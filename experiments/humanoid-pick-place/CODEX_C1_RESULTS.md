# C1: Codex visual controller development result

The signed-in Codex CLI successfully chose structured actions from camera images
and public robot state. The single seed-820 simulator episode achieved **0/1
placements and 0/1 sustained lifts**. Two actions executed; the third was rejected
by the existing collision guard. This establishes an executable CLI control path,
not competent manipulation or a general model comparison.

The user authorized ChatGPT-login Codex decisions without direct API integration.
No API transport, API keys or AGY were used. All five CLI invocations are retained:
two archived-image probes without actions, then three decisions in one fresh
simulator episode. The CLI may make internal network requests; five is an invocation
count, not an API request count.

## Declared condition and outcome

[C1 protocol](protocols/C1.md) and implementation were committed before the episode
at `ad73d1521b12fbb557f6a67dc2cbe9abf91e0bb3`. CLI version 0.154.0 used ChatGPT login,
requested `gpt-5.6-sol` with low reasoning, fixed 960 x 720 RGB, public calibration
and proprioception, and the guarded move/hand/hold interface. The backend snapshot
is not independently identified by the CLI event stream. The budget was 20
invocations and simulated t=25 s, with 120 s timeout per decision and no wrapper retry.

| Measure | Result |
|---|---:|
| Planned / completed episodes | 1 / 1 |
| Placement / sustained lift / strict pass | 0 / 0 / 0 |
| CLI decisions / executed actions / rejected actions | 3 / 2 / 1 |
| Tool calls observed in decision event logs | 0 |
| Final simulation time, including reset | 2.50 s |
| Mean / maximum CLI decision latency | 17.08 / 20.67 s |
| Peak object penetration | 6.291 mm; exceeds 2 mm quality limit |

The process exited normally after saving a failed episode. Exit code zero is not a
task-success result. Private scorer `success` and `lifted` are both false. The
deadline passed; physical task, contact-quality and rejection criteria failed.

## Action trace and interpretation

All positions are world metres and use downward quaternion `[0.5,-0.5,0.5,0.5]`.

| Decision | Requested primitive | Execution |
|---|---|---|
| 1 | Open hand to closure 0, 0.5 s | Completed, t=0.5 to 1.0 s |
| 2 | Move to `[0.25,-0.184,0.82]`, 1.5 s | Completed, t=1.0 to 2.5 s |
| 3 | Move to `[0.245,-0.184,0.755]`, 1.0 s | Rejected; simulation stayed at t=2.5 s |

The third response was valid JSON and within numeric workspace bounds. The guard
rejected its commanded joint path because it predicted robot/environment
penetration over 2 mm. This is a motion-planning failure, not a CLI format failure.

Separately, the private scorer recorded 6.291 mm object penetration at t=2.093 s
during the second, completed action, against `right_hand_middle_0_link`. Its recorded
normal force was 0 N. These are simulator diagnostics, not measured physical damage.
The sampled guard therefore must not be described as guaranteeing the post-hoc
object-contact quality limit on every completed motion.

The episode does not isolate whether image-based localization, hand-site geometry,
or path selection caused the poor approach. No ground-truth correction or scripted
rescue was given to the model. No prompt was changed or episode rerun after the
outcome. A future condition should first diagnose the saved trajectory and clarify
the public grasp-site/path contract before testing another prompt or model.

## Boundary and validation evidence

Every saved episode prompt and PNG reproduced exactly from its allowlisted public
`call_NNN.json` request. All three CLI event logs passed the pinned audit, and all
execution source hashes matched the working source after completion. Each decision
used a fresh temporary public-input directory; shell, tools, web, apps, plugins,
memory and host skill discovery were disabled. No tool activity was observed.
This is configuration and event evidence, not proof of perfect OS-level secrecy.

The first archived probe returned a valid move but was rejected by the audit for
startup notices. It remains a failed integration attempt. The revision suppresses
the unstable-feature warning and permits only the exact disabled-tool-host notice
before a turn. The second archived probe passed, returning a hand command. Neither
probe executed an action or counts toward the one-episode success denominator.

- Full discovery: **212 tests passed in 176.702 s** before final provenance and
  condition-lock adjustments; [log](results/codex_C1_tests.txt).
- Final affected suites: **40 tests passed in 9.065 s**, including ten CLI tests
  and thirty existing runner tests; [log](results/codex_C1_final_targeted.txt).
  One earlier targeted command named a nonexistent test module; the corrected
  command above passed. No test failure was treated as a pass.
- `git diff --check` passed. Historical artifacts and held-out seeds 840–849 remain
  unchanged. The proposed P5 mean-error gate stays at 5.0 mm and remains unmet.

## Retained artifacts and next checklist

[Machine-readable result](results/codex_C1.json) contains the runner report, private
score, per-decision actions, CLI usage/latency, source hashes and archive hashes.
[Episode archive](results/codex_C1_episode.zip) retains all 28 runtime files plus a
per-file SHA-256 manifest. [Both probes](results/codex_C1_probes.zip) retain 15 files
plus a per-file manifest. Runtime originals remain under `runtime/humanoid/codex-C1/`,
`codex-C1-probe/` and `codex-C1-probe-r2/`.

- [x] Confirm signed-in CLI control and qualify the public-input handoff.
- [x] Freeze the C1 source/protocol, execute the declared episode and retain failure.
- [x] Audit logs, source identity, task scoring and rejected-action timing.
- [ ] Diagnose completed-approach penetration and the rejected path using saved
  artifacts, without another model call or fresh episode.
- [ ] Declare a separate successor condition addressing the diagnosed cause;
  keep public inputs, guard thresholds and budgets explicit.
- [ ] Build a matched conventional visual comparator before larger model claims.

See the [runner guide](CODEX_RUNNER.md) and [living plan](PLAN.md). L2 exact-state
results and C1 use different seeds and execution conditions; they are not a paired
API-versus-CLI or exact-state-versus-vision comparison.
