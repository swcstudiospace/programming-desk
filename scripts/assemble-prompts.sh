#!/usr/bin/env bash
# Prepend prompts/_shared/core-directives.xml to each seat source and write
# prompts-assembled/{SEAT}.xml plus prompts/{SEAT}.xml.
# Substitutes {{DEFAULT_BRANCH}} and {{BOT_ID}} in the shared prefix only.
# Substitutes {{DESK_CHANNEL_ID}}, {{SEAT_UUID:<SEAT>}}, {{DESK_GATEWAY_URL}} and
# {{DESK_ROSTER_VERSION}} from the team roster in both the prefix and the seat body.
# Any {{...}} left after substitution is an error: an assembled prompt is what gets installed.
# Elements with audience="build-seats" are kept for SYSTEMS/WEB/ANDROID/IOS/INFRA.
# audience="lead" and audience="quality" are kept only for those seats.
# Unmarked elements stay in every prompt.
#
#   scripts/assemble-prompts.sh [--roster <path>] [--check]
#
#   --roster <path>  Team roster JSON (default: grokbot/rosters/spectrumwebco.json,
#                    or $ROSTER_FILE when set).
#   --check          Assemble into a temp dir and diff against prompts-assembled/ and the
#                    prompts/<SEAT>.xml aliases. Writes nothing. Exit 1 on drift.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$ROOT/prompts/_shared/core-directives.xml"
BRANCH="${DEFAULT_BRANCH:-main}"
ROSTER="${ROSTER_FILE:-$ROOT/grokbot/rosters/spectrumwebco.json}"
MODE="write"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --roster)
      [[ $# -ge 2 ]] || { echo "assemble-prompts: --roster needs a path" >&2; exit 2; }
      ROSTER="$2"; shift 2 ;;
    --roster=*)
      ROSTER="${1#--roster=}"; shift ;;
    --check)
      MODE="check"; shift ;;
    -h|--help)
      sed -n '2,18p' "$0"; exit 0 ;;
    *)
      echo "assemble-prompts: unknown argument $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$CORE" ]]; then
  echo "assemble-prompts: missing $CORE" >&2
  exit 1
fi
if [[ ! -f "$ROSTER" ]]; then
  echo "assemble-prompts: missing roster $ROSTER (pass --roster or set ROSTER_FILE)" >&2
  exit 1
fi

python3 - "$ROOT" "$CORE" "$BRANCH" "$ROSTER" "$MODE" <<'PY'
import difflib, json, pathlib, re, sys, tempfile
root, core_path, branch, roster_path, mode = sys.argv[1:]
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
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_:]+\}\}")

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

def load_roster(path: str) -> dict[str, str]:
    """Placeholder -> value, from grokbot/rosters/<team>.json. Missing keys are an error here,
    not at install time."""
    try:
        doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"assemble-prompts: cannot read roster {path}: {exc}")
    missing = [k for k in ("desk_channel_id", "gateway_url", "roster_version", "seats") if k not in doc]
    if missing:
        raise SystemExit(f"assemble-prompts: roster {path} lacks {', '.join(missing)}")
    values = {
        "{{DESK_CHANNEL_ID}}": str(doc["desk_channel_id"]),
        "{{DESK_GATEWAY_URL}}": str(doc["gateway_url"]).rstrip("/"),
        "{{DESK_ROSTER_VERSION}}": str(doc["roster_version"]),
    }
    for _, seat in seats:
        entry = doc["seats"].get(seat)
        if not isinstance(entry, dict) or not entry.get("uuid"):
            raise SystemExit(f"assemble-prompts: roster {path} has no uuid for seat {seat}")
        values[f"{{{{SEAT_UUID:{seat}}}}}"] = str(entry["uuid"])
    return values

def fill(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace(key, value)
    return text

def unfilled(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in PLACEHOLDER_RE.findall(line):
            found.append((line_no, m))
    return found

roster = load_roster(roster_path)
assembled = root / "prompts-assembled"

rendered: dict[str, str] = {}
for bot_id, seat in seats:
    src = root / "prompts" / f"{bot_id}.xml"
    if not src.exists():
        raise SystemExit(f"assemble-prompts: missing {src}")
    prefix = strip_audience(core, seat).replace("{{DEFAULT_BRANCH}}", branch).replace("{{BOT_ID}}", bot_id)
    prefix = fill(prefix, roster)
    body = fill(src.read_text(encoding="utf-8"), roster)
    text = prefix.rstrip() + "\n" + body
    if not text.endswith("\n"):
        text += "\n"
    left = unfilled(text)
    if left:
        where = "; ".join(f"{name} at line {line_no}" for line_no, name in left[:5])
        raise SystemExit(f"assemble-prompts: {seat}.xml has unfilled placeholder(s): {where}")
    rendered[seat] = text

if mode == "check":
    # Assemble into a temp dir, then diff each result against the committed copies.
    drift: list[str] = []
    with tempfile.TemporaryDirectory(prefix="assemble-prompts-") as tmp:
        tmpdir = pathlib.Path(tmp)
        for _, seat in seats:
            fresh = tmpdir / f"{seat}.xml"
            fresh.write_text(rendered[seat], encoding="utf-8")
            for dest in (assembled / f"{seat}.xml", root / "prompts" / f"{seat}.xml"):
                rel = dest.relative_to(root)
                if not dest.exists():
                    drift.append(f"{rel}: missing")
                    continue
                have = dest.read_text(encoding="utf-8").splitlines(keepends=True)
                want = fresh.read_text(encoding="utf-8").splitlines(keepends=True)
                if have != want:
                    diff = list(difflib.unified_diff(have, want, str(rel), f"assembled/{seat}.xml", n=0))
                    hunk = "".join(diff[2:8]).rstrip()
                    drift.append(f"{rel}: differs from the sources\n{hunk}")
    if drift:
        for line in drift:
            print(f"  - {line}", file=sys.stderr)
        print(f"assemble-prompts --check: {len(drift)} file(s) out of date; "
              f"run scripts/assemble-prompts.sh and commit the result", file=sys.stderr)
        raise SystemExit(1)
    print(f"assemble-prompts --check: {len(seats)} seats up to date "
          f"(roster {pathlib.Path(roster_path).name}, version {roster['{{DESK_ROSTER_VERSION}}']})")
    raise SystemExit(0)

assembled.mkdir(exist_ok=True)
for _, seat in seats:
    for dest in (assembled / f"{seat}.xml", root / "prompts" / f"{seat}.xml"):
        dest.write_text(rendered[seat], encoding="utf-8")
        print(f"wrote {dest.relative_to(root)}")
PY
