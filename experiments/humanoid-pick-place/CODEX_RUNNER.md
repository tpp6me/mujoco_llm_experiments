# Signed-in Codex visual runner

The user chose Codex for both development and robot decisions. The runner invokes
the installed CLI through its ChatGPT login. It contains no HTTP client, SDK,
API-key lookup or AGY dependency. Historical API runners remain archived and are
not the execution path. See [execution policy](../../coordination/EXECUTION_POLICY.md).

`humanoid_sim.codex_policy` attaches a PNG to a fresh non-interactive CLI session.
Public robot state, calibration, remaining budget and previous action outcomes go
in the prompt. A strict JSON action schema constrains the answer. The parent
runner validates the event log and action, then submits it to the existing
fresh-observation and collision guards. A new camera observation follows each
completed action. Private scoring happens after execution and is never feedback
to the model.

The CLI process runs in a temporary directory with only the public PNG and schema.
Its configuration disables tools and instruction/skill discovery. The parent
rejects tool events before acting. Authentication stays with Codex; subprocess
environment variables are allowlisted, excluding API keys and custom endpoints.
The configuration and event parser are pinned to CLI 0.154.0 and reject other
versions until reviewed. This does not make the model deterministic or prove
perfect filesystem isolation; a read-only sandbox alone would not prevent reads.

## Conditions and run modes

The runner supports two experiment conditions via `--condition {c1,c2}` (default: `c1`):
- `c1`: The frozen C1 protocol ([protocols/C1.md](protocols/C1.md)). Preserves the exact original C1 prompt bytes without modification.
- `c2`: The proposed C2 protocol ([protocols/C2_PROPOSAL.md](protocols/C2_PROPOSAL.md)). Preserves C1 prompt bytes and appends the exact nominal robot hand geometry enclosure paragraph before the JSON schema. Generates static robot-only geometry evidence (`geometry_evidence.json`).

Both conditions record condition ID, prompt SHA-256, geometry evidence SHA-256, and source revision in provenance metadata, rejecting any mismatched configuration before execution.

### Local preflight (zero model invocations, zero physics steps)

Default C1 preflight:
```sh
.venv/bin/python -m humanoid_sim.codex_policy --condition c1 --output runtime/humanoid/c1-preflight
```

C2 preflight (validates C2 prompt formatting, geometry evidence, payload isolation, and zero model calls):
```sh
.venv/bin/python -m humanoid_sim.codex_policy --condition c2 --output runtime/humanoid/c2-preflight
```

### Archived-image probe (one decision, no physics action)

```sh
.venv/bin/python -m humanoid_sim.codex_policy --probe experiments/humanoid-pick-place/results/visual_policy_scaffold/demo_request_payload.json --condition c1 --output runtime/humanoid/new-codex-probe
```

### Simulator execution (`--execute`)

A simulator run requires `--execute`. The entry point supports only development seed 820 and the fixed camera. Output directories must be new. macOS rendering uses `mjpython` with graphics access. Signed-in CLI decisions also require network/login access.

Frozen C1 development run:
```sh
.venv/bin/mjpython -m humanoid_sim.codex_policy --execute --condition c1 --output runtime/humanoid/codex-C1/seed-820
```

Proposed C2 frozen run (offline preparation only; requires separate Codex review and freeze before execution):
```sh
.venv/bin/mjpython -m humanoid_sim.codex_policy --execute --condition c2 --output runtime/humanoid/codex-C2/seed-820
```

## Read the artifacts

- `report.json`: termination, CLI invocation count (`model_calls`), guarded action
  accounting, latency and source hashes. Its historical
  `placement_success_claimed=false` field is not the task score.
- `evaluator_report.json`, `episode.npz`, `events.json`, `metadata.json`: private
  post-hoc outcome and simulator trajectory. Never feed these to the controller.
- `call_NNN.json`: public request, response and runner accounting.
- `codex/decision-NNN/`: exact prompt, PNG, final decision, CLI JSONL events, stderr
  and attempt status. Timeouts and failed audits remain in this directory.

Count CLI invocations separately from actions and from unobservable internal
network requests. Report requested model/version without claiming an independently
verified backend snapshot. The CLI condition has no enforced output-token cap and
is not a matched reproduction of L2's API settings.
