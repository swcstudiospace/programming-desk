# RAGFlow ingest on merge

Operator notes for Ming. This file is not named `README.md` because that basename is owned by `bot-06-quality-security` at every depth in `ownership.yaml`. The ingest code, workflow and this note are `bot-05-infrastructure`.

## What runs

`.github/workflows/ragflow-ingest.yml` runs on a push to `main` of programming-desk. It checks out the commit, fetches the push's before SHA when that SHA is 40 hex characters, and runs `infra/ragflow/ingest.py`. A `pull_request` event is not a trigger, and the script exits 0 if `GITHUB_EVENT_NAME` is `pull_request`.

`agent-substrate`, `agent-swarm` and `claude-ultrathink` do not get a workflow until the templates in `infra/ragflow/callers/` are copied into each repo as `.github/workflows/ragflow-ingest.yml`. Those templates call:

`swcstudiospace/programming-desk/.github/workflows/ragflow-ingest.yml@main`

programming-desk is public, so another repository in the org can call that file. If the desk repo is later made private, GitHub's Actions policy has to allow reusable workflows from this repository. The caller job needs `contents: read` only.

## Secrets

Set these on each repository that runs the job. Name them exactly:

- `RAGFLOW_URL` — key-protected public RAGFlow API origin, no path
- `RAGFLOW_API_KEY` — bearer token for that API

Pass both from the caller template. When either value is empty, the script prints `RAGFLOW_URL or RAGFLOW_API_KEY is empty; skipping ingest` and exits 0. Pull requests and forks do not need the secrets. The script never prints the key or file contents.

Do not put the values in the workflow file, the caller template, or a receipt.

## Reachability

This job runs on `ubuntu-latest` and calls the public API. It does not use the VPS runner and it does not SSH anywhere.

If RAGFlow later drops its public hostname, a GitHub-hosted runner cannot reach it. The option then is a self-hosted runner that is already on the tailnet: change `runs-on` in `.github/workflows/ragflow-ingest.yml` to that runner's labels and keep the same secrets. This change does not do that, and it does not change the VPS.

Hosted Actions minutes on this org have been blocked before. If the job sits queued, that is billing, not a failed ingest. The desk gate workflows already use the self-hosted runner for that reason; this ingest job stays on the hosted runner until Ming chooses the tailnet option above.

## What gets stored

The dataset name is the repo name (`programming-desk`, and `agent-skills` for `SKILL.md` and agent files). Product repos (`kanbanos`, `desklanes`, `clippyos`, `auctioning`, plus the hyphenated aliases) also copy README and `docs/` into `product-docs`.

The document name is `repo__path` with slashes written as `__`. Doc types keep their suffix. Other text types get `.txt` appended. `meta_fields` are `repo`, `path`, `commit`, `url`, and `content_sha256`.

A file is skipped when it sits in an excluded directory (including `.receipts` and `transcripts`), has a secret-like name, is over 400 KB, or its bytes match a credential shape. A matching `content_sha256` is left in place. A changed file is uploaded, tagged, and only then the previous document id is deleted. Removed paths are deleted. Parsing is requested in batches of 16.

## Dry run

From a checkout, with no secrets required:

```bash
python3 infra/ragflow/ingest.py \
  --repo programming-desk \
  --root . \
  --before "$(git merge-base origin/main HEAD)" \
  --after HEAD \
  --dry-run
```

`--before` accepts a SHA or a single ref (`origin/main`). An all-zero before, the GitHub placeholder for a new branch, lists the whole tree. A feature branch compared with `origin/main` directly includes commits that landed on main after the branch point; the merge-base above is that branch's own diff.

## Rollback

Revert the merge commit. Documents already parsed stay in RAGFlow until a later push deletes those paths; reverting the workflow stops new ingests and does not itself call the delete API. No database migration is involved. Recovery is the time it takes to merge the revert.
