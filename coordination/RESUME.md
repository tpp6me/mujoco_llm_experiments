# Resume here — project handoff

Updated 2026-09-15. The user paused after C3 execution/review and requested that a
new session be able to continue from the repository. **Task011 is accepted and
integrated; Task012 is ready but not launched.** No further model trial is scheduled.
The Task011 worker exited normally at 03:42:53 UTC. Its completed run is preserved;
do not resume it as a way to start another episode.

The latest experiment/results checkpoint before this handoff is main `5f07785`.
This handoff is a later documentation-only commit. Use the latest main, not an old
task worktree, as the starting point for new authorized work.

## Read order

1. [Execution policy](EXECUTION_POLICY.md): user preferences and authorization boundaries.
2. [Humanoid living plan](../experiments/humanoid-pick-place/PLAN.md): full phase checklist.
3. [C3 result and interpretation](../experiments/humanoid-pick-place/CODEX_C3_RESULTS.md).
4. [Task011 acceptance](agy/reviews/011-acceptance.md): independent checks and limits.
5. [Task012 brief](agy/tasks/012-c3-grasp-audit.md): the next bounded offline task.
6. [AGY workflow/register](agy/WORKFLOW.md): earlier tasks and completion/review process.

## User preferences that carry forward

- Minimize Codex implementation overhead; maximize AGY implementation, debugging,
  targeted tests, artifact preparation and documentation. Codex owns experiment
  design, review/integration, scientific interpretation and every VLA decision.
- AGY means Antigravity; the user described its model as Gemini 3.8 Flash. It has
  repository/git access. Automatic permissions for bounded task briefs, including
  task-branch commits/pushes, were explicitly authorized. AGY does not merge main.
- No direct OpenAI API calls, API-key lookup or paid API transport. Use signed-in
  Codex CLI for VLA only under a separately reviewed/frozen execution brief. Historical
  API adapters/results remain evidence, not permission to execute them.
- Use isolated AGY worktrees and complete handoffs with exact tips. Codex independently
  checks material claims, returns focused revisions when needed, then integrates.
  Do not start another experiment to repair a failure or improve a reported score.
- The user is pausing, not asking to execute Task012 now. Wait for their next instruction.

## Current scientific state

The long-term aim is to assess LLM visual-action control of a humanoid picking an
object into a basket, extending the earlier SO101 work. Current experiments use
MuJoCo, a supported/fixed-pelvis G1, one arm/hand, red block and basket. Walking,
free-standing balance and continuous-time humanoid control remain future phases.
The language model chooses guarded Cartesian move/hand/hold primitives; IK and
actuator execution are conventional code, not direct model-generated torques.

The conventional G2 controller achieved 100/100 placements and 97/100 strict passes
through the shared interface using exact state and a developed recipe. Thus physical
feasibility is demonstrated under that assistance, not solved visual manipulation.

| Visual condition | Decisions / completed actions | Lift / placement | Peak object penetration |
|---|---:|---:|---:|
| C1: original visual prompt | 3 / 2 | 0/1 / 0/1 | 6.291 mm |
| C2: nominal hand geometry and reassessment guidance | 9 / 8 | 0/1 / 0/1 | 5.185 mm |
| C3: assessment plus command in the same response | 18 / 17 | 0/1 / 0/1 | 1.611 mm |

Each is one reused seed820 development episode and ended on a guard rejection.
C3 stopped at t=13.700 s. Its object-penetration/deadline criteria pass, but placement,
sustained lift and strict task success do not. No causal improvement or population
success rate follows from these three conditions.

C3 preserved all 18 valid assessments; no malformed/missing response, refusal or
unknown execution outcome. The first close (action4) displaced the block 86.244 mm
in XY and tipped it about 90 degrees. Later close/lift actions13/14 left it effectively
stationary. The final move was rejected before execution. This points to unresolved
visual/hand-geometry and grasp-verification problems, without identifying internal
model beliefs. Task012 investigates their physical details from saved evidence.

## Latest discussion: SO101, humanoids and Astra

The user asked whether Astra controls SO101 reasonably well but fails on humanoids.
The supported conclusion is narrower: assisted SO101 tasks worked better than the
current G1 visual grasping setup, under different task/information conditions.

- **C1–C3 requested gpt-5.6-sol, low reasoning, CLI 0.154.0—not Astra.** The CLI logs
  identify requested settings, not an independently resolved backend snapshot.
- Earlier interactive SO101 results do not record an exact runtime model identifier;
  do not retroactively label them an Astra benchmark solely from session assumptions.
- SO101 structured-state sorting passed 9/9 episodes with a known motion recipe and
  paused time. Continuous visual sorting made 16/16 correct target selections but
  only 6/16 physical rejections, principally due to late commands. Later robustness
  results also retain failures. This is conditional competence, not general reliability.
- SO101 benefited from known coordinates or calibrated pixel-to-plane conversion and
  an established sequence. G1 visual control lacked that recipe and needed more
  demanding hand/object alignment judgments. The model, assistance, tasks and timing
  were not held constant. No matched Astra-on-both-robots conclusion is justified.

Sources: [SO101 Phase3](../experiments/conveyor-color-sorting/PHASE3_RESULTS.md),
[Phase5](../experiments/conveyor-color-sorting/PHASE5_RESULTS.md),
[Phase6](../experiments/conveyor-color-sorting/PHASE6_RESULTS.md),
[C1](../experiments/humanoid-pick-place/CODEX_C1_RESULTS.md),
[C2](../experiments/humanoid-pick-place/CODEX_C2_RESULTS.md),
[C3](../experiments/humanoid-pick-place/CODEX_C3_RESULTS.md).

## C3 evidence and immutable review order

- Frozen execution commit: `19b78537ff52b348f30a10e5147ab5012c5c1ef1`.
- Accepted AGY Task011 tip: `7710356d183928c1cad005bb338d956c27c1d2ce`.
- Blind labels committed before unblinding: `cd2c4888a8b56469a69263db6a30c9e93f3b7bfc`.
- [C3 archive](../experiments/humanoid-pick-place/results/codex_C3_episode.zip):
  SHA-256 `08202990a01ecd22adc2c860ff2260b126bfae57579963285bba6595e7198972`;
  137 runtime files plus sha256.json (138 members). Includes manifest, stdout/stderr,
  exit status, 18 prompts/images/responses/events, private scorer and trajectory.
- [C3 freeze](../experiments/humanoid-pick-place/protocols/C3_FREEZE.json) pins 92
  source/model/input files. Proposal and frozen protocol remain unchanged.
- [Blind labels](agy/reviews/011-blind-labels.json), [comparison](agy/reviews/011-assessment-comparison.json),
  [independent audit](agy/reviews/011-independent-review.json), [private endpoint analysis](agy/reviews/011-private-trajectory-review.json).

All 18 first-pass images were labelled without consulting associated model answers,
commands, private outcomes or trajectory. Those labels are immutable. Relation
agreement: 9/18 overall, 9/11 when both judgments are determinate; reviewer/model
abstentions are 6/18 and 1/18. Visibility agreement: 6/18, largely due to consistent
reviewer marking of basket-rim occlusion as partly_visible. Uncertainty is not an
established model error; these are reviewer interpretations, not validated ground truth.

The AGY machine summary/completion retain historical pending-review wording and
recorded hashes. Task011 acceptance and the C3 results report supersede that status;
do not rewrite the archived trial to make every status field look current.

## Next authorized work when the user resumes

Follow [Task012](agy/tasks/012-c3-grasp-audit.md). Create a fresh
`agy/012-c3-grasp-audit` worktree from then-current clean main. AGY should audit the
pinned archive's failed closes and action18 rejection using scratch forward kinematics,
compare requested/achieved poses, and retain source/input/artifact hashes and tests.
No new model request, reset, physics step, live render or controller/guard change.
Codex reviews and chooses any successor condition; no C4 is frozen or authorized.

Use the existing interpreter at `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`.
The user authorized AGY batch operation via `/Users/praveen/.local/bin/agy` with
`--dangerously-skip-permissions`, `--print-timeout`, and a complete task prompt.
Use a fresh AGY conversation for Task012. Previous launches used a small Python
subprocess wrapper with an argv list, task-worktree cwd, stdout/stderr logs and an
atomic status.json; preserve completion/exit status and monitor through review.
Do not resume Task011's conversation to execute another C3 episode.

Previous local worktrees exist under `/private/tmp/mujoco-llms-agy-001` through
`...-011` (006 was cancelled). They are convenience checkouts, not required inputs.
Task010's latest tip is `9d9e087`; Task011's is `7710356`. Do not edit an old worktree
or delete unrelated work merely to resume this project.

## Reproduce without temporary runtime directories

All evidence required for Task012 is in the committed C3 ZIP. Verify its pinned
hash, extract to a new directory, then verify every member against sha256.json.
Do not depend on `/private/tmp/agy-011-execution` or an old ignored runtime folder.
The recorded Task011 runtime path was
`/private/tmp/mujoco-llms-agy-011/runtime/humanoid/codex-C3/seed-820`.

For the existing full evidence checker, use a checkout of execution commit
`19b7853`, extract the archive into that checkout's `runtime/humanoid/codex-C3/`,
and invoke the checker from latest main, passing that checkout to --worktree:

```sh
.venv/bin/python coordination/agy/reviews/011-independent-check.py --worktree /path/to/execution-checkout --output /private/tmp/c3-verification.json
.venv/bin/python coordination/agy/reviews/011-private-trajectory-check.py --episode /path/to/execution-checkout/runtime/humanoid/codex-C3/seed-820 --output /private/tmp/c3-endpoints.json
```

These scripts read saved evidence; they do not execute robot actions or models.
The endpoint checker additionally verifies the pinned archive and frozen inputs.
Fresh environments need the repository's pinned dependencies; .venv is local and
intentionally not committed. Do not commit credentials, caches or duplicate runtime data.

## Validation history and boundaries

Task010 passed 45 independently rerun guarded offline tests. Its initial AGY batch
had violated the no-physics brief by running existing reset/physics-backed tests;
Codex stopped it, required fake fixtures/guards, and retained a boundary record.
Do not summarize all Task010 work as zero physics. The final guarded verification
and preflight used no new dynamics/model decisions. Task011 then separately authorized
one real simulator episode with Codex VLA, whose evidence-only review needed no
broad software suite.

For Task012, guard Environment construction/reset, mj_step/mj_step1/mj_step2 and
live model launches before selecting tests. mj_forward on scratch data is allowed.
Whole unittest discovery includes physical integration tests and is not suitable
for an offline-only brief. Do not rerun already-passing suites without a relevant change.

The separate P5 perception gate remains **unmet at 5.8715 mm versus <=5.0 mm**.
Seeds 840–849 remain unused. Preserve all historical failures, thresholds, budgets,
archives and blind labels. No physical hardware, free-standing or walking capability
has been demonstrated by these supported-body simulator results.
