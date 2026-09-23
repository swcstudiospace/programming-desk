#!/usr/bin/env bash
# Prepend prompts/_shared/core-directives.xml to each seat source and write
# prompts-assembled/{SEAT}.xml plus prompts/{SEAT}.xml.
# Substitutes {{DEFAULT_BRANCH}} and {{BOT_ID}} in the shared prefix only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$ROOT/prompts/_shared/core-directives.xml"
BRANCH="${DEFAULT_BRANCH:-main}"

if [[ ! -f "$CORE" ]]; then
  echo "assemble-prompts: missing $CORE" >&2
  exit 1
fi

python3 - "$ROOT" "$CORE" "$BRANCH" <<'PY'
import pathlib, sys
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
assembled = root / "prompts-assembled"
assembled.mkdir(exist_ok=True)
for bot_id, seat in seats:
    src = root / "prompts" / f"{bot_id}.xml"
    if not src.exists():
        raise SystemExit(f"assemble-prompts: missing {src}")
    prefix = core.replace("{{DEFAULT_BRANCH}}", branch).replace("{{BOT_ID}}", bot_id)
    body = src.read_text(encoding="utf-8")
    text = prefix.rstrip() + "\n" + body
    if not text.endswith("\n"):
        text += "\n"
    for dest in (assembled / f"{seat}.xml", root / "prompts" / f"{seat}.xml"):
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest.relative_to(root)}")
PY
