#!/usr/bin/env bash
# Consistency check for the desk production loop skill and the pack docs that restate it.
#
# The rules in this skill are load-bearing and have already drifted twice under review: a
# degraded-mode trigger that made every successful gateway brief degraded, and an event kind that
# reported a blocker for finished work. Prose cannot be unit-tested, but it can be asserted
# against: this script fails if a rule goes missing, if a superseded wording survives somewhere
# else in the file, or if a seat template picks up a raw docs/memory connector.
#
# Run from the repository root. Cited by
# .receipts/bot-00-programming-lead/lead-production-loop-spe-4794.json.
#
#   bash skills/desk-bootstrap/desk-production-loop/verify.sh
set -euo pipefail
cd "$(dirname "$0")/../../.."
python3 - <<'PY'
import re,sys
from pathlib import Path
def load(p): return Path(p).read_text()
S=load("skills/desk-bootstrap/desk-production-loop/SKILL.md")
B=load("skills/desk-bootstrap/SKILL.md")
D=load("docs/desk-operating-model.md")
V=load("docs/vps-agent-bus.md")
R=load("grokbot/README.md")
G=load("scripts/generate-templates.py")
T={p.stem:p.read_text() for p in sorted(Path("grokbot/templates").glob("*.md"))}
# prose checks run on whitespace-collapsed, emphasis-stripped text so a line wrap cannot fake a pass
flat=lambda s: re.sub(r"\s+"," ",s.replace("**","").replace("*",""))
fS,fD,fV,fR=flat(S),flat(D),flat(V),flat(R)
def need(c,m):
    if not c: sys.exit("FAIL: "+m)
need(S.startswith("---\nname: desk-production-loop\ndescription: "),"frontmatter")
pos=[S.index(t) for t in ("memory_brief","memory_write","events_emit","handoff_to_hermes")]
need(pos==sorted(pos),"phase order")
for t in ("memory_brief","memory_write","events_emit","handoff_to_hermes"): need(t in D,"phase in doc "+t)
# round 2 (a) — success is judged on nested error fields, not the envelope
need("A populated response is not a successful brief" in fS,"R2a envelope rule skill")
need("A populated response is not a successful brief" in fD,"R2a envelope rule doc")
need("There is no top-level `reason`. Do not look for one." in fS,"R2a no top-level reason")
for f in ("substrate.error","recall.error"): need(f in S and f in D,"R2a field "+f)
# round 3 — per-bank recall failures: the Hindsight path never sets recall.error
need("recall.results[].error" in S,"R3 per-bank field skill")
need("recall.results[].error" in D,"R3 per-bank field doc")
need("One failed bank is enough" in fS,"R3 one-bank rule skill")
need("one failed bank is enough" in fD.lower(),"R3 one-bank rule doc")
need("returns early" in fS and "returns early" in fD,"R3 early-return reason")
need("recall.error is never set" in fD or "recall.error` is never set" in fD,"R3 doc never-set")
need("What this list covers, and what it cannot" in fS,"R4 qualified coverage note")
need("this table is what has to grow with it" in fS,"R3 growth rule")
# round 4 — per-bank reason path, and the silent local-store default
need("recall.results[<bank>].reason" in S,"R4 per-bank reason path")
need("recall.results[<bank>].reason" in D,"R4 per-bank reason path doc")
need("with the bank name" in fS,"R4 name the bank")
need("cannot fail loudly" in fS,"R4 silent default")
need("json.JSONDecodeError" in S,"R4 store reader cited")
need("empty or unreadable, indistinguishable" in fS,"R4 indistinguishable")
# round 5 — the round-4 remedy was circular and destructive; it must stay deleted
need("There is no second tool that settles it" in fS,"R5 no second tool")
need("the same call the brief made" in fS,"R5 roster_status same call")
need("A write, not a check" in fS,"R5 write-not-check")
need("never diagnose with a write" in fS,"R5 never diagnose with a write")
need("desk_roster_status` for LEAD's queue, a pack load/unload call for" not in S,"R5 bad remedy removed")
need("complete for `desk_brief`" not in fS,"R4 stale completeness claim removed")
# round 2 (b) — generated_at is a read timestamp, never an etag, no change detection
need("read timestamp, not a revision id" in fS,"R2b skill")
need("read timestamp, not a revision id" in fD,"R2b doc")
need("brief_read_at" in S and "brief_read_at" in D,"R2b field")
need("never in `brief_etag`" in fS,"R2b never brief_etag")
need("change detection is not available" in fS,"R2b no change detection")
need("never recorded as `brief_etag` and never diffed" in fD,"R2b doc rule")
# round 1 (a) — etag-less tool is not degraded; (b) event routing; (c) doctor gap
need("A successful brief from a tool whose contract has no etag field is not degraded" in fS,"R1a")
need("Degraded mode is the brief failing" in fS,"R1a degraded def")
i=S.index("| Completed, brief degraded, ack recorded |");row=S[i:S.index("\n",i)]
need("implementation.completed" in row and "ticket.blocked" not in row,"R1b routing row")
need("signalled in the payload, never by swapping the kind" in fS,"R1b rule")
need("Degradation is signalled in the event payload, never by swapping the event kind" in fD,"R1b doc")
need("_declared_skills" in G and "_declared_skills()" in S,"R1c doctor gap")
# original ticket requirements
for raw in ("user-ragflow","user-hindsight"): need(raw in S and raw in R,"raw connector "+raw)
need("skills.approve" in S and "skills.approve" in D and "skills.approve" in R,"skills.approve")
need("list and invoke" in fS,"list/invoke")
for f in ("packet_version","packet_payload_sha256","packet_signed_at","packet_key_id","packet_signature"):
    need(f in S and f in V,"packet "+f)
need("SPE-4792" in S and "SPE-4792" in V and "SPE-4792" in D,"SPE-4792")
need("desk-production-loop" in G and "desk-production-loop/SKILL.md" in B,"wiring")
for s,x in T.items():
    need("- desk-production-loop\n" in x,s+" enables loop")
    need(not re.search(r"(?i)(ragflow|hindsight-api|user-hindsight|user-ragflow)",x),s+" names raw server")
# superseded wording must be gone, so a fixed defect cannot quietly survive elsewhere in the file
for dead in ("the response carried no etag; or the connector did not list the tool",
             "generated_at is the brief's revision stamp",
             "desk_brief.generated_at=",
             '{} with reason: "substrate unreachable"'):
    need(dead not in fS,"stale text still present: "+dead[:40])
need("or one with no etag" not in fD,"stale doc text")
need(not re.search(r"(?i)(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN|Bearer\s+[A-Za-z0-9]{8})",S+B+D+V+R+"".join(T.values())),"credential literal")
print("ok: frontmatter, phase order, R2a nested-error test, R3 per-bank recall, R2b read-timestamp semantics, R1a etag/degraded split, R1b event routing, R1c doctor gap, raw-connector denial, skills.approve, 5 packet fields, 7/7 templates, no stale wording, no credential literal")
PY
