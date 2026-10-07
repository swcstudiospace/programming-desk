# LLM red-team scanning — stub (SPE-5162)

Status: **stub only**. No garak (or PyRIT) job runs today, in CI or anywhere else.

## Why this exists

SPE-5162 hardens the PR-level security gate (secrets, SAST, SCA) and adds an optional nightly
DAST job. LLM red-teaming is a different shape of check — slow, noisy, and aimed at model
behaviour rather than code — and belongs on neither the PR gate nor the nightly DAST job. This
file is the placeholder that keeps that decision visible instead of it being an unlisted gap.

## What garak is, briefly

[garak](https://github.com/leondz/garak) is an LLM vulnerability scanner: it probes a model or
an LLM-backed endpoint for prompt injection, jailbreaks, data leakage, and similar failure
modes, and reports which probes succeeded.

## Plan (not built yet)

- **Target**: an LLM-facing surface once one exists in a form that can be scanned without live
  production traffic — `services/desk-gateway` is the current candidate once it exposes such a
  surface.
- **Cadence**: weekly, scheduled — never on every PR. These tools take minutes-to-hours per run
  and produce findings that need a human to triage, which is exactly what does not belong in a
  PR gate (see `.github/workflows/security-pr.yml`'s own note against a full offensive suite on
  every PR).
- **Alternative to evaluate alongside garak**: [PyRIT](https://github.com/Azure/PyRIT)
  (Microsoft's Python Risk Identification Tool), which covers similar ground with a different
  probe/attack strategy model. Evaluate both against the actual target surface before picking
  one rather than committing to either sight unseen.
- **Owner**: QUALITY (`bot-06-quality-security`), same as the rest of `ci/security/**`.

## Explicitly out of scope for SPE-5162

- Any garak or PyRIT job actually running, scheduled or otherwise.
- AutoRedTeam or any other full offensive-security suite on every PR — that is precisely what
  the PR gate in this ticket is designed *not* to be.
