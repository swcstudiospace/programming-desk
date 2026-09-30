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

## Greptile P1s on the first commit

Three P1s were raised against the ack fix above, all valid, all fixed in the second commit:

- **4141224505 — long threads blocked recovery.** GitHub lists issue comments oldest-first and
  will not reverse them, so a lookup starting at the beginning spent its whole page budget on
  the oldest comments and never reached the reply. That stranded the intake: every retry read
  unknown, refused to post, and never advanced. The lookup now carries a `since` window
  anchored a day before the first attempt for that ack, so the thread's length stops mattering.
  `Store.intake_delivery` keeps `first_at` across attempts for exactly this reason, and drops it
  for a state meaning nothing was sent.
- **4141224477 — concurrent acks could both post.** The delivery record was read before the
  post and written after it, so two calls for the same reply could both read a pre-post state —
  the second one's lookup finding nothing precisely because the first one's comment had not
  landed yet. Acks are now serialised per intake+ack and the record is re-read inside that lock.
- **4141224494 — an unknown outcome advanced the intake.** With an attempt recorded and the
  GitHub token gone, the lookup could not say whether the reply landed, and the code still let
  the intake advance — marking it acknowledged on the chance that it had. Any lookup that
  cannot answer, unconfigured included, now fails closed with `notify_unknown`.

## Verification

`uv run pytest -q` in `services/desk-gateway`: **99 passed**, exit 0.

Each P1 fix has its own negative control: dropping the `since` window strands the intake at
`notify_unknown`; removing the per-ack lock posts two identical comments; restoring the
`not_configured` early return advances the intake on an unreadable outcome.

The GitHub fake is wired under `HttpUpstream.request` rather than over `GitHub`'s methods, so
the real `comment_on_issue` and `find_issue_comment` run and the paging and `since` window are
exercised rather than assumed.

Earlier round, first commit only: `uv run pytest -q` → 96 passed, exit 0.

Both fixes have negative controls: reverting `tools/lead.py` and `tools/infra.py` to `dcac9c0`
and re-running the new tests fails with `the retry posted the reply a second time` and
`['dep-staging'] == ['dep-prod']` respectively, so the tests are keyed on the defects.

G-1 ownership and G-3 secrets pass on the changed files; `ci/tests/test_gates.py` is green
(157 passed). See the JSON receipt for exit codes, claims and what is unverified.
