# Exact-state LLM development pilot

Executed: 2026-09-12. **The API-connected L2 pilot is complete.**
GPT-5.6 Sol completed 0/3 placements, with sustained lift in 1/3 cases.
The matched conventional G2 policy completed 3/3 placements, with 2/3 strict passes.
This is a small development pilot, not a confirmatory model comparison.

## Matched outcomes

| Seed | Conventional task / strict | LLM task / strict | LLM lift | LLM calls | LLM termination |
|---|---|---|---|---|---|
| 700 | Pass / Pass | Fail / Fail | No | 7 | Reached 25 s without a sustained lift |
| 701 | Pass / Pass | Fail / Fail | No | 4 | Guard rejected a lowering move at 3.5 s |
| 702 | Pass / Fail | Fail / Fail | Yes | 7 | Guard rejected the lowering move at 8.2 s |

The conventional seed-702 placement exceeded the 2 mm object penetration limit
(2.125 mm), so it remains a strict failure despite completing the task. LLM peak
object penetration was 7.938, 8.050 and 4.007 mm respectively; no LLM episode passed
the independent quality gate. All outcomes and rejected actions remain archived.

The recorded actions show that seed 700 moved/closed the hand and then spent the
remaining time holding; the object finished on the ground, without a sustained
lift. Seed 701 ended when the guard rejected a further lowering request. Seed 702 achieved
a sustained lift and moved toward the basket, but its requested lowering pose
was rejected. These are descriptions of recorded actions and physics, not claims
about the model's hidden reasoning or general ability.

## Conditions and accounting

Both controllers started from identical randomized integration setups on seeds
700–702. Their complete public initial observations were checked for equality.
They used the same version-2 interface, world coordinates, 25-second simulated
deadline, 20-action maximum and terminal rejection rule. The conventional policy
used its qualified recipe; the LLM chose individual primitives from its own
observations/history. No tuned recipe or object-offset correction was supplied
to the model. The runner added only version fields and request IDs.

The model saw exact object/basket state and robot proprioception, plus the static
task/controller contract. It saw no images, private scorer fields, conventional
trajectories or source files, and had no filesystem or external tools. This tests
exact-state sequencing and action control, not vision-language-action performance.
Physics paused during calls; no free-standing balance, walking or real-time
performance was measured. Source/prompt/schema hashes matched the frozen L2
configuration throughout the pilot.

All **18 L2 API responses completed**, each reporting model `gpt-5.6-sol`.
There were no API errors, refusals, response parsing failures or budget stops in L2.
Provider-reported usage totalled **125,528 input tokens and 2,300 output tokens**.
The estimated L2 token cost was **$0.548112**. Summed API round-trip wall time was
**88.495 seconds**; this includes network/provider overhead and is not isolated
inference time. Cost uses the documented standard rates recorded in the protocol
and is not an invoice. Each call's exact request, raw response, IDs, usage,
returned model and timing are retained.

## L1 integration failure is separate

The initial L1 pilot produced three HTTP 400 `invalid_json_schema` errors before
returning model output. A separate diagnostic request identified a missing
explicit string type in the action discriminators. L2 added that type; it did
not change the prompt, model settings or action capabilities. L1 is an integration
failure, not evidence of failed model manipulation. Its conventional outcomes,
three rejected API requests and diagnostic remain archived.

Unknown usage in L1 and the diagnostic retains conservative cost reservations.
L2 used a $4.50 local limit, leaving room within the original $5 estimate envelope.
No failed episode or model-selected action was retried within either pilot.
L2 reused the same three cases as a declared development run after the API fix.

## Evidence and reproduction

- [L2 complete outcomes](results/llm_L2.json), [all requests/actions/responses](results/llm_L2_attempts.zip),
  [frozen source](results/llm_L2_source.zip), [protocol](protocols/L2.md).
- [L1 outcomes](results/llm_L1.json), [attempts](results/llm_L1_attempts.zip),
  [diagnostic](results/llm_L1_api_diagnostic.json), [source](results/llm_L1_source.zip),
  [protocol](protocols/L1.md).
- [60-test log before L2](results/llm_L2_tests.txt), [runner guide](LLM_RUNNER.md),
  [results index](RESULTS_INDEX.md), [living checklist](PLAN.md).

Runtime trajectories are local under `runtime/humanoid/llm-L1/` and
`runtime/humanoid/llm-L2/`, with separate conventional/LLM directories per seed.
Attempt ZIPs preserve JSON artifacts, not full trajectory arrays. Use the archived
source/dependency versions to reproduce a configuration; provider model aliases
and sampling mean new responses need not match. Replays use saved physics states.

## What this supports and what comes next

The shared interface and automatic live API loop are working. This pilot exposed
approach/grasp and collision-aware action-selection failures under the current
prompt; it does not establish that LLMs generally cannot control the task.
One successful lift also does not establish complete manipulation capability.

Next, inspect the failed actions and audit the hand-site/grasp geometry contract.
Develop any prompt or capability changes on these now-used cases, label recipe-
assisted conditions separately, and freeze a larger matched benchmark on new
seeds before drawing comparative conclusions. The mechanical controller's 97/100
G2 qualification remains historical evidence on a different seed set.

Replay labels were corrected after scoring to identify the acting controller/model.
The [61-test final log](results/llm_L2_final_tests.txt) and
[replay-code snapshot](results/llm_replay_source.zip) retain that visualization-only
change; no scored episode was rerun.

The seed-702 LLM replay is `runtime/humanoid/llm-L2/seed-0702/llm/pick_place.mp4`.
Its 247 frames (8.233 s, 960 × 720, 30 fps) decoded without errors. The lift
frame was inspected and the overlay correctly identifies GPT-5.6 Sol, exact-state
control and fixed pelvis. The clip ends at the rejected action; no placement is claimed.
