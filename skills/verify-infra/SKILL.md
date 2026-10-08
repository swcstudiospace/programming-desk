---
name: verify-infra
description: Prove an infrastructure change from a plan and read-only health checks. Use for INFRA seat work. Does not redeploy or change variables.
bots: [bot-05-infrastructure]
gates: [G-2]
---

# Verify infra

## L1 — Summary

**Read the plan. Do not apply it to prove you read it.** A live change is
G-5 or G-6. Verification of the plan is not that change.

**Decision tree:**

```
About to claim the infrastructure is healthy or the plan is safe?
├─ The proof is a plan or a read?
│   ├─ PLAN ──▶ fmt, validate, and a plan you read. Not apply.
│   └─ READ ──▶ status, logs, unit state, or DB health from the INFRA roster.
├─ The proof needs a redeploy or a variable edit? ──▶ Stop. G-6. Not this skill.
└─ The credential or the cluster is missing? ──▶ unverified names which one.
```

Apply the proof standard in `skills/verify/SKILL.md`. Plan rules live in
`skills/platforms/terraform-k8s/SKILL.md`. Railway and VPS read rules live in
`skills/platforms/railway-tailscale/SKILL.md`.

---

## Launch

Open `contracts/tool-rosters/infra.yaml` and use only the read tools listed
there. Fill `skills/verify/references/feature-map-template.md` when a person
can observe the change (a port answering, a unit active). This checkout has
no infra verify helper beyond the roster reads below. Do not invent a
command for one. Desk Infra stays read-only on live systems: no deploys, no
variable changes, no runner changes.

## Doctor

Confirm the gateway listed the tool you are about to call. The read tools
this skill may cite:

| Tool | What it returns | What it must not return |
|---|---|---|
| `desk_railway_status` | Services, latest deployment, health | A redeploy |
| `desk_railway_logs` | Bounded, redacted log lines | A secret you then paste into the receipt |
| `desk_railway_variable_names` | Variable names | Variable values. Names only |
| `desk_tailscale_status` | Forwarders, ports, tags | A tailnet name, a tailnet address, or a host you were not shown |
| `desk_vps_units` | systemd state for the units you name | A restart |
| `desk_db_health` | Health of the data-plane services | A connection string |

`desk_railway_redeploy` is g5. Doctor does not call it. Changing a Railway
variable is out of this skill. Do not write a `*.railway.internal` host, a
tailnet name, or a token into the receipt, the PR, or a log (PD-4).

For a Terraform tree, Doctor confirms `fmt -check` and `validate` can run.
If the cloud credential is absent, the plan is inconclusive. Do not invent a
plan.

## Drive

1. **Plan path.** Run `terraform fmt -check`, `terraform validate`, and
   `terraform plan`. Read every resource (`skills/platforms/terraform-k8s/SKILL.md`).
   Record the plan. A `-/+` on a stateful resource is a stop for human
   approval (G-6), not a thing this skill applies. Do not `terraform apply`.
   Do not `terraform destroy`. Do not `kubectl delete`.
2. **Read path.** Call the roster tool that matches the claim. Capture the
   action (the call) and the resulting state (the status or the health
   field). A log line that shows the process up is the state; a guess that
   it "should be up" is not.
3. **Side effects.** If the change was supposed to open a port or flip a
   unit, the read after the change has to show that. Do not mock the health
   endpoint you are trying to prove.
4. A dry run of apply is still not apply, and it is not proof that apply
   would be safe. Do not put `--dry-run` in a receipt command (G-2).

## Evidence

Save the plan output and the read-tool result under
`.verify-evidence/<task-id>/`. `output_tail` names the file and must not
contain a secret, a variable value, a tailnet name, or a private host.
Redact before the receipt is written. Do not commit the directory.

## Cleanup

Do not redeploy to "put it back" as cleanup. Rollback of a live change is a
G-5 plan with an approval, owned by the change that deployed, not by this
skill. Leave the live system as you found it.

## Where it runs

| Runner | What it can host | Unverified line |
|---|---|---|
| Linux cloud agent | `fmt -check` and `validate` when the toolchain and the checkout are present. Roster reads when the gateway listed them | `no cloud credentials: plan not run` or `roster read not run: tool not listed` |
| Self-hosted VPS runner | The same reads. This skill does not install an emulator image or change the runner | `plan not run: self-hosted VPS runner` |
| GitHub-hosted `ubuntu-latest` | Public-repo plan jobs when the workflow exists and credentials are provided to that workflow | `plan not run: no workflow in this checkout` |
| Ming's Mac | Private-repo plan, when credentials are present | `no cloud credentials: Ming's Mac` |

A plan you did not execute is not "the plan is empty." Say you did not run it.

## Receipt mapping

| Observation | Field |
|---|---|
| `terraform fmt -check`, `validate`, `plan` | `commands[]` with the exit codes you saw. The claim "the plan was read" cites the plan command, not fmt |
| A roster read | its own command. `output_tail` is redacted and names the artifact |
| Redeploy, apply, variable edit | not a command in this skill's receipt. Those need `approvals[]` and a `rollback_plan` on a change that is allowed to do them (G-5, G-6) |
| Credential or tool missing | `unverified` with the row above |
| Reproduce-first failure | `expects_failure: true` |
