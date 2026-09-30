#!/usr/bin/env bash
# Consistency check for the desk production loop skill and the pack docs that restate it.
#
# The rules in this skill are load-bearing and have drifted in every review round so far: a
# degraded-mode trigger that made every successful gateway brief degraded, an event kind that
# reported a blocker for finished work, a "no top-level reason" rule that left a call-level refusal
# with nothing to quote, and a memory write described as atomic when it is two planes with an
# any() over them. Prose cannot be unit-tested, but it can be asserted against: this script fails
# if a rule goes missing, if a superseded wording survives somewhere else in the file, if a seat
# template is missing or picks up a raw docs/memory connector, or if the skill and the pack docs
# that restate it drift apart.
#
# What it cannot do: assert that a rule is CORRECT, or that a seat follows it. Every round's defect
# would have passed the previous round's version of this check. It is a drift alarm, not a proof.
#
# Not wired into CI: .github/workflows/** is bot-05-infrastructure's under ownership.yaml, so LEAD
# cannot add the step. Recorded in the receipt's `unverified` as an INFRA/QUALITY ask; run it by
# hand, and from the receipt, until then.
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
# The seven seat templates are named explicitly, not globbed. A glob over an empty or partial
# directory runs zero per-template checks and then reports "7/7 templates" on the strength of
# nothing -- the check has to fail when a template is MISSING, which is exactly the case a glob
# cannot see. This list is the SEATS table in scripts/generate-templates.py; if a seat is added
# there, it is added here too, and the mismatch check below is what says so.
SEAT_TEMPLATES=["ANDROID","INFRA","IOS","LEAD","QUALITY","SYSTEMS","WEB"]
TEMPLATE_DIR=Path("grokbot/templates")
missing=[s for s in SEAT_TEMPLATES if not (TEMPLATE_DIR/f"{s}.md").is_file()]
if missing: sys.exit("FAIL: missing seat template(s): "+", ".join(f"grokbot/templates/{s}.md" for s in missing))
found=sorted(p.stem for p in TEMPLATE_DIR.glob("*.md"))
if found!=sorted(SEAT_TEMPLATES): sys.exit(f"FAIL: grokbot/templates holds {found}, expected {sorted(SEAT_TEMPLATES)}")
# and the expected list must still be the generator's own seat list, or this file is the stale one
gen_seats=sorted(re.findall(r'^\s*\("bot-0\d-[a-z0-9-]+",\s*"([A-Z]+)"', G, re.M))
if gen_seats!=sorted(SEAT_TEMPLATES): sys.exit(f"FAIL: generate-templates.py SEATS is {gen_seats}, SEAT_TEMPLATES here is {sorted(SEAT_TEMPLATES)}")
T={s:(TEMPLATE_DIR/f"{s}.md").read_text() for s in SEAT_TEMPLATES}
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
# round 6 — the no-top-level-reason rule is TRUE of a completed brief (Shape B) and FALSE of a
# call-level refusal (Shape A). It must stay scoped to Shape B, never stated unconditionally.
need("no top-level `reason`. Do not look for one" in fS,"R6 no top-level reason (Shape B)")
need("There is no top-level `reason`. Do not look for one." not in fS,"R6 unscoped no-reason rule removed")
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
# --- round 6 ---------------------------------------------------------------------------------
# (a) call-level vs nested brief failures: two shapes, discriminated on the top-level error key
need("Shape A" in fS and "Shape B" in fS,"R6a shape names skill")
need("Shape A" in fD and "Shape B" in fD,"R6a shape names doc")
need("The discriminator is the top-level `error` key" in fS,"R6a discriminator")
for code in ("unknown_tool","deadline","backend_missing","invalid_args","secret_refused","forbidden","internal"):
    need(code in S,"R6a call-level code "+code)
for code in ("unknown_tool","deadline","backend_missing"): need(code in D,"R6a doc call-level code "+code)
i=S.index("| Failure | Quote from | Name it as |");tbl=S[i:S.index("\n\n",i)]
need("the **top-level** `reason`" in tbl,"R6a top-level reason row in reason-path table")
need("recall.results[<bank>].reason" in tbl,"R6a per-bank row survives in same table")
need("four places a `reason` can live" in fS,"R6a four reason places")
need("top-level `reason`, with its `error` code" in fD,"R6a doc top-level reason path")
# (b) no etag => not a failed brief, but repo work still needs the degraded ack; never silent
need("A successful brief from a tool whose contract has no etag field is not a failed brief" in fS,"R6b not-failed")
need("It is also not a licence to work" in fS,"R6b not a licence")
need("brief_no_revision_marker" in S and "brief_no_revision_marker" in D,"R6b no-marker blocker code")
need("degraded-loop: repo work on a brief with no revision marker" in S,"R6b no-marker ack operation")
need("degraded-loop: repo work without a memory brief" in S,"R6b failed-brief ack operation")
need("Never proceed to an edit on `generated_at` and `cached` alone" in fS,"R6b no silent proceed skill")
need("no seat proceeds to an edit on `generated_at` and `cached` alone" in fD,"R6b no silent proceed doc")
need("A successful brief from a tool whose contract has no etag field is not degraded" not in fS,"R6b stale etag licence removed")
# (c) memory writes are not atomic: per-plane results, uncertain outcomes, no idempotency key
need("It is not atomic, and `ok: true` is not proof" in fS,"R6c not atomic")
need("ANY, not all" in S,"R6c any-not-all cited")
need("So read `results`, not `ok`" in fS,"R6c read results")
need("An error is not proof that nothing was retained" in fS,"R6c error is not proof")
need("There is no idempotency key, so a blind retry can duplicate the fact" in fS,"R6c no idempotency key")
need("results.hindsight" in S and "results.substrate" in S,"R6c per-plane fields")
need("Partial success" in S,"R6c partial success row")
need("evidence_required" in S and "secret_refused" in S,"R6c local refusals named")
need("not atomic" in fD and "if either plane accepted" in fD,"R6c doc any-plane rule")
# (d) emitted events: the gateway collapses every kind to note; payload.event is the routing field
need('"kind": "note"' in S,"R6d note literal cited")
need("payload.event" in S and "payload.event" in D,"R6d payload.event field")
need("the catalogue kind is not the routing field" in fS,"R6d heading rule")
need("This is a documented contract gap, not a design" in fS,"R6d gap named")
need("a seat must not claim its emission routed anywhere" in fS,"R6d no routing claim")
need("never set `seat`, `event` or `task_id`" in fS.replace("Never","never"),"R6d injected keys")
need("The catalogue routes on kind, so swapping it misroutes the turn" not in fS,"R6d stale typed-routing claim removed")
need("catalogue routes on kind; a misrouted turn" not in fS,"R6d stale gate-mapping routing claim removed")
# (e) distinct payload fields: blocker code vs upstream reason vs its path
for f in ("blocker","upstream_reason","reason_path"): need(f in S and f in D,"R6e payload field "+f)
need("One field per meaning" in fS,"R6e one field per meaning")
need("Do not use a bare `payload.reason` for either" in fS,"R6e no bare reason")
need('payload.reason: "brief_degraded"' not in S,"R6e stale overloaded reason removed")
# (f) absent cached means false
need("An absent `cached` means `false`" in fS,"R6f cached absent skill")
need("an absent `cached` means `false`" in fD,"R6f cached absent doc")
need("the fresh path never sets" in fS,"R6f fresh path")
# round 2 (b) — generated_at is a read timestamp, never an etag, no change detection
need("read timestamp, not a revision id" in fS,"R2b skill")
need("read timestamp, not a revision id" in fD,"R2b doc")
need("brief_read_at" in S and "brief_read_at" in D,"R2b field")
need("never in `brief_etag`" in fS,"R2b never brief_etag")
need("change detection is not available" in fS,"R2b no change detection")
need("never recorded as `brief_etag` and never diffed" in fD,"R2b doc rule")
# round 1 (a) — etag-less tool is not degraded; (b) event routing; (c) doctor gap
need("Degraded mode needs a human ack" in fS,"R1a degraded section")
i=S.index("| Completed, degraded (either §3 condition), ack recorded |");row=S[i:S.index("\n",i)]
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
print("ok: frontmatter, phase order, R2a nested-error test, R3 per-bank recall, R2b read-timestamp semantics, R1a etag/degraded split, R1b event routing, R1c doctor gap, R6a call-level vs nested shapes, R6b no-marker ack, R6c non-atomic memory write, R6d payload.event routing gap, R6e distinct payload fields, R6f absent cached, raw-connector denial, skills.approve, 5 packet fields, all 7 named seat templates present, no stale wording, no credential literal")
PY
