---
name: desk-uplift-on
description: Turn the autonomous double uplift back on
disable-model-invocation: true
---

Desk uplift control. Every non-trivial prompt to LEAD runs the full pipeline again: first uplift, 5-8 GoT nodes, 4-8 CoT steps each, Notion/Linear materialisation, second uplift, dispatch.

Run this with your shell tool, from the repository root, and reply with its output only:

```sh
python3 .claude/hooks/desk_uplift.py on
```

The path is repository-relative on purpose. The upstream `ultrathink-*` commands resolve through
`${CLAUDE_PLUGIN_ROOT}`, which is unset in a bare clone — and a bare clone is the case this desk
has to work in, since the repository URL is pasted straight into a Grok Bot. If the command above
fails because you are not at the repository root, `cd` to the git toplevel and run it again. Do
not search the filesystem for another copy of `desk_uplift.py`.

This changes the trigger, not the pipeline. `skills/gotxcot-uplift` is still the procedure and
`vendor/ultrathink-policy/` is still the policy; these verbs only decide when the hook fires.
