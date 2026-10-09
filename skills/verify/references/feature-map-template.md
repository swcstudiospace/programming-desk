# Feature map entry

One file per feature. Copy this file, replace the title with the feature a person
can name, and fill every section before Drive. A map that was not driven end to
end is a plan, and a plan is not proof (G-2).

## Sub-features

The slices a person can tell apart. Name each one. A slice missing from this
list was not covered by this file, so it cannot appear as a passing claim.

## How to get to it (user POV)

The path a person takes from a cold open: the screens, the URL, or the command
they actually type. A developer shortcut that skips this path belongs in
Gotchas, not here, because the proof is the path the person takes.

## Driving it with <harness>

Replace `<harness>` in this heading with the tool that drives the path. Script
the steps so a reviewer can re-run them. For each step record the action and
the state that should follow it. A step that only says the screen "loads" does
not name the state, so it cannot back a claim.

## Gotchas

What a dry run skips, which exit code is a skip rather than a pass, and which
runner cannot host this feature. Those gaps go to the receipt `unverified`
list with the reason. A dry run that prints an argv and exits 0 did not
execute the check.
