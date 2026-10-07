---
name: desk-uplift-skip
description: Skip the uplift for the next message only
disable-model-invocation: true
---

Desk uplift control. Arms a one-shot skip. The message after this one is not uplifted; everything after that is. Use for a quick question mid-build without changing the mode.

Run this with your shell tool, from the repository root, and reply with its output only:

```sh
python3 .claude/hooks/desk_uplift.py skip
```

The path is repository-relative on purpose. The upstream `ultrathink-*` commands resolve through
`${CLAUDE_PLUGIN_ROOT}`, which is unset in a bare clone — and a bare clone is the case this desk
has to work in, since the repository URL is pasted straight into a Grok Bot. If the command above
fails because you are not at the repository root, `cd` to the git toplevel and run it again. Do
not search the filesystem for another copy of `desk_uplift.py`.

This changes the trigger, not the pipeline. `skills/gotxcot-uplift` is still the procedure and
`vendor/ultrathink-policy/` is still the policy; these verbs only decide when the hook fires.
