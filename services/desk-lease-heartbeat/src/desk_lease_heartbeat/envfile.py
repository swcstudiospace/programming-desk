"""systemd EnvironmentFile parser.

The cron fallback cannot source the env file: systemd's format is not shell,
and a token containing ``$``, a backtick or a quote would be expanded or would
abort the wrapper. This parser assigns bytes the way EnvironmentFile does and
does not expand anything.
"""

from __future__ import annotations

from pathlib import Path


class EnvFileError(ValueError):
    """The file is not a systemd EnvironmentFile."""


def parse_env_file(text: str) -> dict[str, str]:
    """Parse ``text`` into assignments. Values are literal, including ``$``."""
    if text.startswith("\ufeff"):
        text = text[1:]
    values: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        key, sep, rest = line.partition("=")
        key = key.strip()
        if sep != "=" or not _valid_key(key):
            raise EnvFileError(f"line {lineno}: expected KEY=VALUE")
        values[key] = _parse_value(rest, lineno)
    return values


def load_env_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EnvFileError(f"cannot read {path}: {exc.strerror}") from exc
    return parse_env_file(text)


def _valid_key(key: str) -> bool:
    if not key:
        return False
    first, rest = key[0], key[1:]
    if not (first.isascii() and (first.isalpha() or first == "_")):
        return False
    return all(ch.isascii() and (ch.isalnum() or ch == "_") for ch in rest)


def _parse_value(rest: str, lineno: int) -> str:
    body = rest.lstrip(" \t")
    if not body:
        return ""
    if body[0] == '"':
        return _double_quoted(body, lineno)
    if body[0] == "'":
        return _single_quoted(body, lineno)
    # Unquoted: the rest of the line, with trailing whitespace removed.
    # No expansion. An embedded comment is part of the value; quote it to be sure.
    return body.rstrip(" \t")


def _double_quoted(body: str, lineno: int) -> str:
    out: list[str] = []
    i = 1
    while i < len(body):
        ch = body[i]
        if ch == '"':
            trailing = body[i + 1 :].strip()
            if trailing:
                raise EnvFileError(f"line {lineno}: trailing characters after quoted value")
            return "".join(out)
        if ch == "\\":
            if i + 1 >= len(body):
                raise EnvFileError(f"line {lineno}: dangling backslash in quoted value")
            nxt = body[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    raise EnvFileError(f"line {lineno}: unterminated double quote")


def _single_quoted(body: str, lineno: int) -> str:
    end = body.find("'", 1)
    if end < 0:
        raise EnvFileError(f"line {lineno}: unterminated single quote")
    trailing = body[end + 1 :].strip()
    if trailing:
        raise EnvFileError(f"line {lineno}: trailing characters after quoted value")
    return body[1:end]
