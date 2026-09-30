# C-2 · `desk_receipt_approve` reads at one sha and writes at another

**Owner:** bot-01-systems-backend · **File:** `services/desk-gateway/src/desk_gateway/tools/quality.py`
**Severity:** this one loses committed work. Take it before C-1.

## The defect

`receipt_approve` and `_commit_file` do not share a view of the branch. There is no sha carried
between them, and the write is unconditional.

```python
# receipt_approve — reads at the fetched sha (call it T1)
await repo.fetch()
ref = f"{repo.remote}/{args['branch']}"
text = await repo.show(args["receipt_path"], ref)       # ← content as of T1
...
receipt["approved_by"] = ctx.bot_id                      # stamp applied to the T1 content
push = await _commit_file(ctx, args["branch"], args["receipt_path"],
                          json.dumps(receipt, indent=2) + "\n", ...)
```

```python
# _commit_file — clones the branch AGAIN (T2), then overwrites
clone = await run_command(["git", "clone", "--quiet", "--depth", "1",
                           "--branch", branch, remote, str(scratch / "wt")], timeout=90)
target = wt / rel_path
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(content, encoding="utf-8")             # ← blind overwrite, no compare
await run_command(["git", "add", "-f", rel_path], cwd=str(wt))
...
push = await run_command(["git", "push", "-q", "origin", f"HEAD:{branch}"], ...)
```

If the branch moves between T1 and T2 — a seat pushing a tip-fix, which on this PR happened on
every round — then:

1. the clone holds the **new** receipt,
2. `write_text` replaces it with the **T1** receipt plus the stamp,
3. the push is an ordinary fast-forward on top of the new head, so it **succeeds**, and
4. every receipt change made in between is gone, with the stamp now attached to content that was
   never on the branch.

No error surfaces. `{"pushed": True, "commit": <sha>}` comes back and the call looks clean. The
gates ran against T1, so the committed bytes are not the bytes that were gated either — which is
the same class of problem as C-1, one step further along.

## Patch

Carry the read sha, and refuse to write over anything else. Two parts.

**1. Capture the sha `text` was read at**, beside the `repo.show` call:

```python
read_sha = await repo.rev_parse(ref)        # or: run_command(["git","rev-parse",ref], cwd=repo.dir)
text = await repo.show(args["receipt_path"], ref)
```

**2. Give `_commit_file` an `expect_sha` and an `expect_content`, and abort on either mismatch.**
Inside, after the clone and before the write:

```python
head = await run_command(["git", "rev-parse", "HEAD"], cwd=str(wt))
if expect_sha and head["stdout"].strip() != expect_sha:
    # the branch moved under us; the caller gated content that is no longer current
    return {"pushed": False, "reason": "stale_read",
            "expected": expect_sha, "found": head["stdout"].strip()}
if expect_content is not None and target.exists() \
        and target.read_text(encoding="utf-8") != expect_content:
    return {"pushed": False, "reason": "stale_read", "detail": f"{rel_path} changed since it was read"}
```

and have `receipt_approve` pass `expect_sha=read_sha, expect_content=text`, turning a `stale_read`
into a caller-visible failure:

```python
if not push.get("pushed") and push.get("reason") == "stale_read":
    return failure("stale_read",
                   "the branch moved after the receipt was read and gated; re-run the approval "
                   "against the new tip", push=push)
```

The content check is the belt to the sha's braces: a `--depth 1` clone of a branch that moved is
cheap to get a stale sha from, and comparing the file itself is what actually protects the bytes.
`--force-with-lease` is **not** a substitute — the push here is a legitimate fast-forward, so a
lease would allow it; the problem is the working-tree write, not the ref update.

## How to tell it worked

A regression test with no gateway needed: write a receipt to a scratch branch, read it, push a
different version of the same file to that branch, then call the commit helper with the first
read's sha and content. Before the patch it pushes and the second version is gone; after, it
returns `stale_read` and the branch is untouched.

## Note for whoever takes this

C-1 (the preflight ordering) is in the same function. If you take C-1 alone, this defect gets
*easier* to hit, because first stamps start succeeding where they previously all failed at the
preflight. Taking C-2 first, or both together, avoids that window.
