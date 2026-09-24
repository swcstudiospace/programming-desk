#!/usr/bin/env bash
# Prepend prompts/_shared/core-directives.xml to each seat source and write
# prompts-assembled/{SEAT}.xml plus prompts/{SEAT}.xml.
# Substitutes {{DEFAULT_BRANCH}} and {{BOT_ID}} in the shared prefix only.
# Elements with audience="build-seats" are kept for SYSTEMS/WEB/ANDROID/IOS/INFRA.
# audience="lead" and audience="quality" are kept only for those seats.
# Unmarked elements stay in every prompt.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$ROOT/prompts/_shared/core-directives.xml"
BRANCH="${DEFAULT_BRANCH:-main}"

if [[ ! -f "$CORE" ]]; then
  echo "assemble-prompts: missing $CORE" >&2
  exit 1
fi

python3 - "$ROOT" "$CORE" "$BRANCH" <<'PY'
import pathlib, re, sys
root, core_path, branch = sys.argv[1:]
root = pathlib.Path(root)
core = pathlib.Path(core_path).read_text(encoding="utf-8")
seats = [
    ("bot-00-programming-lead", "LEAD"),
    ("bot-01-systems-backend", "SYSTEMS"),
    ("bot-02-web-edge", "WEB"),
    ("bot-03-android", "ANDROID"),
    ("bot-04-ios", "IOS"),
    ("bot-05-infrastructure", "INFRA"),
    ("bot-06-quality-security", "QUALITY"),
]
BUILD = {"SYSTEMS", "WEB", "ANDROID", "IOS", "INFRA"}

def audience_applies(aud: str, seat: str) -> bool:
    if aud == "build-seats":
        return seat in BUILD
    if aud == "lead":
        return seat == "LEAD"
    if aud == "quality":
        return seat == "QUALITY"
    raise SystemExit(f"assemble-prompts: unknown audience {aud!r}")

def skip_element(xml: str, i: int, name: str) -> int:
    """i is just after an opening tag. Return the index just after its matching close."""
    depth = 1
    n = len(xml)
    open_re = re.compile(rf"<{re.escape(name)}\b[^>]*?/?>")
    close = f"</{name}>"
    while i < n and depth:
        if xml.startswith("<!--", i):
            j = xml.find("-->", i)
            if j < 0:
                raise SystemExit("assemble-prompts: unclosed comment while skipping")
            i = j + 3
            continue
        if xml.startswith("<![CDATA[", i):
            j = xml.find("]]>", i)
            if j < 0:
                raise SystemExit("assemble-prompts: unclosed cdata while skipping")
            i = j + 3
            continue
        if xml.startswith(close, i):
            depth -= 1
            i += len(close)
            continue
        m = open_re.match(xml, i)
        if m:
            tok = m.group(0)
            i = m.end()
            if not tok.endswith("/>"):
                depth += 1
            continue
        i += 1
    if depth:
        raise SystemExit(f"assemble-prompts: unclosed <{name}>")
    return i

def strip_audience(xml: str, seat: str) -> str:
    """Omit elements whose audience attribute does not include this seat.

    Every other byte is copied unchanged, including comments and CDATA.
    """
    out: list[str] = []
    i = 0
    n = len(xml)
    while i < n:
        if xml.startswith("<!--", i):
            j = xml.find("-->", i)
            if j < 0:
                raise SystemExit("assemble-prompts: unclosed comment")
            out.append(xml[i:j + 3])
            i = j + 3
            continue
        if xml.startswith("<![CDATA[", i):
            j = xml.find("]]>", i)
            if j < 0:
                raise SystemExit("assemble-prompts: unclosed cdata")
            out.append(xml[i:j + 3])
            i = j + 3
            continue
        if xml[i] == "<" and not xml.startswith("</", i) and not xml.startswith("<?", i):
            j = xml.find(">", i)
            if j < 0:
                raise SystemExit("assemble-prompts: unclosed tag")
            tag = xml[i:j + 1]
            name_m = re.match(r"<([A-Za-z_][\w:.-]*)\b", tag)
            aud_m = re.search(r'\baudience="([^"]+)"', tag)
            if aud_m and name_m and not audience_applies(aud_m.group(1), seat):
                if tag.endswith("/>"):
                    i = j + 1
                    continue
                i = skip_element(xml, j + 1, name_m.group(1))
                continue
            out.append(tag)
            i = j + 1
            continue
        out.append(xml[i])
        i += 1
    return "".join(out)

assembled = root / "prompts-assembled"
assembled.mkdir(exist_ok=True)
for bot_id, seat in seats:
    src = root / "prompts" / f"{bot_id}.xml"
    if not src.exists():
        raise SystemExit(f"assemble-prompts: missing {src}")
    prefix = strip_audience(core, seat).replace("{{DEFAULT_BRANCH}}", branch).replace("{{BOT_ID}}", bot_id)
    body = src.read_text(encoding="utf-8")
    text = prefix.rstrip() + "\n" + body
    if not text.endswith("\n"):
        text += "\n"
    for dest in (assembled / f"{seat}.xml", root / "prompts" / f"{seat}.xml"):
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest.relative_to(root)}")
PY
