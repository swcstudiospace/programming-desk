# SYSTEMS — post-land P2s: intake ack idempotency, Railway env scoping

Base: `main` @ `dcac9c0`. Owned paths only: `services/desk-gateway/**`, `.receipts/bot-01-systems-backend/**`.

## P2 4141126604 — the origin reply could be posted twice

`desk_intake_ack` posts the GitHub reply *before* advancing the intake, which is correct — a
failed reply must not leave an intake marked accepted that nobody was told about. The cost of
that ordering is that the reply becomes the thing a retry can duplicate: the comment succeeds,
`store.intake_ack` fails, the tool tells LEAD to call again, and the second call posts an
identical comment because nothing recorded that the first one landed.

The reply is now delivered at most once per ack:

- Before posting, a `attempted` delivery marker is written to the intake record as a write of
  its own (`Store.intake_delivery`). The post is only reached once that write is durable, so
  no later failure can lose the fact that a comment may exist — and if the marker write is
  what fails, nothing was posted and there is nothing to duplicate.
- On success the marker becomes `delivered`, and a retry of the same ack skips the post and
  only finishes the advance.
- If even the `delivered` write is lost, the retry sees `attempted` and asks the issue, which
  is the real record: the comment carries a matching HTML-comment marker
  (`<!-- desk-intake-ack <id> <status> <digest> -->`), so finding it proves delivery.
- An outcome that cannot be read back — a lookup error, or a thread longer than the pages
  `GitHub.find_issue_comment` walks — fails closed with `notify_unknown` and posts nothing. An
  unknown is exactly the case that double-posts.

The key is a digest of the ack arguments, so a retry of the same call is suppressed while a
deliberately different ack (a later status, a new message) is still a reply that goes out.

## P2 4141126611 — `latest_deployment` could name the wrong environment

`railway_status` reported `latest_deployment` as whichever service instance the API listed
first, across all environments. Railway returns one instance per environment in no guaranteed
order, so on a service with staging alongside production that field could be staging's — and
`railway_logs` fell back to it, serving staging logs under the production service's name.

`latest_deployment` is now scoped to one environment and says which: production when the
project has one, else the single/first listed, by the same rule `_find_service` already used to
pick the environment to read variables from or redeploy into. `deployments` still carries every
environment. `_find_service` returns that environment's deployment, so `railway_logs` and the
`railway_redeploy` staleness check act on the environment they report. Nothing deployed in the
chosen environment is `not_found` naming it, not a silent read of another environment;
`deployment_id` passed explicitly still reads whatever it names.

## Verification

`uv run pytest -q` in `services/desk-gateway`: **96 passed**, exit 0.

Both fixes have negative controls: reverting `tools/lead.py` and `tools/infra.py` to `dcac9c0`
and re-running the new tests fails with `the retry posted the reply a second time` and
`['dep-staging'] == ['dep-prod']` respectively, so the tests are keyed on the defects.

G-1 ownership and G-3 secrets pass on the changed files; `ci/tests/test_gates.py` is green
(157 passed). See the JSON receipt for exit codes, claims and what is unverified.
