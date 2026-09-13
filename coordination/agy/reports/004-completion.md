# AGY completion — task 004

Status: **ready for review**
Task brief: `coordination/agy/tasks/004-visual-policy-scaffold.md`
Branch: `agy/004-visual-policy-scaffold`
Starting commit: `9c143d45625e0780206fd64a7771daf0633e7671`
Implementation commit: `03f84e1f4a51a2da28e39db0ce42fb4d8c7acc77`
Worktree: `/private/tmp/mujoco-llms-agy-004`

---

## Changes and rationale

Task 004 implements a provider-neutral offline RGB-to-action visual policy loop with an injected model callable, strict public request allowlist, fresh-observation / guarded-action execution, budget/deadline termination handling, and comprehensive verification tests.

### 1. Visual policy runner module (`humanoid_sim/visual_policy_runner.py`)
- **Narrow session adapter (`VisualPolicySession`)**: Wraps `VisualSession` to authoritatively enforce the pilot limits ($20$ calls maximum, $25.0$ s simulated deadline with millisecond rounding `ceil(seconds / 0.001) * 0.001`). If limits are exceeded, the pending observation is consumed/invalidated and a rejected response is returned. It delegates to `VisualSession.execute(observation_id, request)` so observation freshness and the interface preflight collision guard remain authoritative.
- **Strict allowlist construction (`build_public_payload`)**:
  - `allowlist_camera`: extracts only `width`, `height`, `projection`, `camera_world_xyz_m`, `world_to_camera_rotation`, `focal_xy_px`, `principal_xy_px`, and `axes`.
  - `allowlist_robot`: extracts only `joint_names`, `joint_position_rad`, `joint_velocity_rad_s`, `hand_xyz_m`, `hand_quaternion_wxyz`, and `contact_links`.
  - `allowlist_robot_state`: extracts only `schema_version`, `instruction_version`, `mode` (`robot_state`), `time_s`, `frame` (`world`), `supported_body`, and `robot`.
  - `allowlist_observation`: extracts only `schema_version`, `observation_id`, `time_s`, `camera`, `robot_state`, `rgb_png_base64`, and `rgb_sha256`.
  - `sanitize_action_for_history` and `sanitize_response_for_history`: sanitize public commands and execution responses.
  - Never serializes the environment, simulator state, task truth, object pose, private scorer, source file paths, or diagnostic objects. Deliberately planted private fields are completely stripped.
- **Visual prompt (`VISUAL_PROMPT`)**: Adapted from exact-state L2. Explicitly informs the policy that RGB visual observations and robot proprioception are provided, while ground-truth object coordinates, basket coordinates, and oracle feedback are excluded. Preserves identical robot capabilities, workspace boundaries, primitive definitions (`move`, `hand`, `hold`), downward hand orientation, duration limits, and settling requirements.
- **Response parsing and validation (`parse_and_validate_response`)**:
  - `strict_json`: parses JSON strictly, rejecting duplicate keys and non-finite constants (`NaN`, `Infinity`).
  - Validates command schema: verifies action in `('move', 'hand', 'hold')`, exact required argument keys, finite numbers, duration in $[0.02, 10.0]$ s, workspace bounds for `move`, unit quaternion norm ($|\text{norm}-1.0| \le 10^{-4}$), and closure in $[0.0, 1.0]$.
  - Distinguishes model refusal (`ModelRefusalError`) and malformed output (`MalformedResponseError`).
- **Loop execution (`run_visual_episode`)**:
  - For each step, checks call/time limits, captures fresh observation, builds public allowlist payload, records pending call record, invokes injected callable with wall-clock timing, parses command, executes via `VisualPolicySession.execute(observation_id, request)`, appends sanitized history, and writes reviewable `call_NNN.json`.
  - Explicit termination on refusal, malformed JSON/command, unhandled exception, interface rejection, deadline, or call limit. Zero silent retries, replacement actions, or oracle fallbacks.
  - Distinguishes model wall latency (`wall_latency_s`, `total_wall_latency_s`) from paused simulation time.
  - Completely separates post-hoc simulation score (`evaluator_report.json`) from policy outputs (`report.json`), and records `placement_success_claimed: false`.
- **Named stubs (`get_named_stub`)**:
  - `scripted`: deterministic 4-step sequence (hold $\to$ approach move $\to$ partial hand closure $\to$ hold) for plumbing tests.
  - `hold`, `refusal`, `malformed`, `exception`, `collision`.
- **CLI entrypoint (`main`)**: Accepts `--output`, `--seed`, `--stub`, `--camera`, `--max-calls`, `--deadline`. Implements an explicit guard rejecting held-out seeds in $840$–$849$.

### 2. Comprehensive documentation (`experiments/humanoid-pick-place/VISUAL_POLICY_RUNNER.md`)
- Defines the public request contract, allowlist specifications, execution loop, freshness enforcement, pilot limits, stub limitations, run instructions, and artifact structure.
- Details the precise work remaining for a future live provider adapter, credential isolation, token billing, protocol freeze, and conventional vision comparator.

### 3. Verification suite (`tests/test_humanoid_visual_policy_runner.py`)
- 16 fast, focused unit and integration tests covering:
  - Allowlist extraction and exclusion of planted private fields in observations and history.
  - Fresh observation capture, exact ID matching, and single-use consumption.
  - Stale/reused observation ID rejection without movement.
  - Explicit termination on model refusal, malformed response, unhandled exception, and collision guard rejection.
  - Call limit ($3$ calls) and deadline budget enforcement ($25.0$ s with millisecond rounding).
  - Injectable clock latency tracking vs paused simulation time.
  - Zero network calls and zero credential access in offline mode.
  - Rejection of false placement success claims.
  - Rejection of duplicate JSON keys and non-finite constants.
  - CLI rejection of held-out seeds $840$–$849$.
  - Development smoke check on seed 820 with separate evaluator report retention.

### 4. Retained development demo and request example
- Located under `experiments/humanoid-pick-place/results/visual_policy_scaffold/`:
  - `call_001.json` through `call_004.json`: complete step-by-step audit trail.
  - `report.json`: overall run report with `placement_success_claimed: false` and provenance metadata.
  - `evaluator_report.json`: separate post-hoc scorer report.
  - `demo_request_payload.json`: exact serialized public request payload example.
  - `episode.npz`, `metadata.json`, `events.json`: physical simulation records.

### 5. Plan and results index updates
- `experiments/humanoid-pick-place/PLAN.md`: checked off Task 004 under Next Actions and added dated progress log entry.
- `experiments/humanoid-pick-place/RESULTS_INDEX.md`: added Visual Policy Runner Scaffolding (Task 004) entry.

---

## Validation

All checks were executed using the primary project virtual environment interpreter:
`/Users/praveen/work/github/mujoco-llms/.venv/bin/python` from `/private/tmp/mujoco-llms-agy-004`.

### 1. Baseline discovery check
- Command: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v`
- Outcome: **145 tests passed in 168.222 s** (baseline intact before changes).

### 2. Focused visual policy runner suite
- Command: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_humanoid_visual_policy_runner.py -v`
- Outcome: **16 tests passed in 6.046 s**.

### 3. Development smoke check on seed 820
- Command:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.visual_policy_runner \
    --output experiments/humanoid-pick-place/results/visual_policy_scaffold \
    --seed 820 \
    --stub scripted \
    --max-calls 4
  ```
- Outcome: Completed with exit code 0. Executed 4 calls and 4 completed actions. Output retained in `experiments/humanoid-pick-place/results/visual_policy_scaffold/`.

### 4. Full repository test discovery
- Command: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v`
- Outcome: **161 tests passed in 172.568 s**. All 145 baseline tests and all 16 new tests pass cleanly.

---

## Experiment evidence and boundary audit

- **Dataset and seed provenance**: Evaluated exclusively on already-developed seed 820 and synthetic test fixtures. Held-out seeds 840–849 remain untouched and protected by an automated CLI guard.
- **Offline isolation**: Offline execution was verified via socket and HTTP urlopen patches, confirming zero network calls and zero credential access.
- **Input isolation**: Deliberately planted private fields (`secret_object_truth`, `task_state`, `score`, `private_scorer_report`, `private_diagnostics`, `oracle_cam`) in observations, robot states, cameras, and history were proven to be stripped completely at the allowlist boundary.
- **Observation freshness**: Single-use observation ID enforcement was verified; executing a command with a stale or reused ID is rejected with `Stale or unknown visual observation` without advancing simulation time or joint positions.
- **Honest reporting**: Completed moves by the scripted stub are recorded as `completed_actions: 4`, while `placement_success_claimed: false` is strictly enforced. The private task score resides exclusively in `evaluator_report.json` and is never returned through policy history or request payloads.
- **Estimator independence**: The runner is independent of the unqualified temporal pose estimator (passive P5 development mean remains 5.8715 mm against the 5.0 mm gate; disconnected from control).

---

## Limitations and next checkpoint

- **Scaffolding status**: The offline stubs verify software plumbing, freshness checks, collision guards, and failure handling. They do not perceive RGB or close a visual control loop.
- **No live model claims**: No vision-language model was called, and no claim that an LLM can perform the manipulation task is made.
- **Next checkpoint**:
  1. Build a live provider adapter translating the provider-neutral `public_payload` into vendor-specific multimodal API formats (e.g. OpenAI Responses, Anthropic Messages, Google Gemini).
  2. Implement multimodal token cost estimation and rate limit reservations.
  3. Author and freeze a formal visual pilot protocol on development seeds before considering any held-out evaluation.
  4. Build a matched conventional vision comparator using equivalent visual inputs.

---

## Review resolution (R1 & R2)

Date: 2026-09-13.
Review reference: `coordination/agy/reviews/004-review.md` (`de853df` on main).
Reviewed tip: `89006428b1a3762993cb882fbf2acc2ef533afa8`.

### R1 — Whole-episode failure accounting
- **Lifecycle protection**: `run_visual_episode` wraps the entire episode iteration (capture, observation validation, payload building, model execution, response parsing, pre-execution duration checks, guarded execution, and outcome sanitization) in a protected `try ... finally` block. A final `report.json` is guaranteed to be written upon any error or termination condition with accurate stage-specific reasons and attempt counters.
- **Diagnostic JSON preservation**: Added `to_json_safe(val)` and updated `write_json(path, value)`. If raw responses contain non-finite floats (`NaN`, `Infinity`, `-Infinity`) or unserializable objects, they are safely converted to diagnostic representations (`{"__diagnostic_nonfinite__": "NaN"}`) and written atomically as compliant JSON without raising `ValueError` or masking errors.
- **Strict numeric validation**: All primitive numeric fields (`seconds`, `closure`, `xyz_m`, `quaternion_wxyz`) now explicitly reject boolean types (`True`/`False`), preventing silent coercion to `1.0` or `0.0`.
- **Robust envelope parsing**: In `parse_and_validate_response`, provider-style envelope structures (e.g. `{'output': None}`, missing arguments, non-list message content) are safely checked and normalized to `MalformedResponseError` without unhandled `TypeError`.
- **Execution exception & evaluator handling**: Exceptions in `session.execute` are caught, logged in `call_NNN.json` as `execution_exception`, and reported without retry; simulation time reflects actual physics time reached (`session.env.data.time`). Evaluator save exceptions are captured in `report['evaluator_error']` rather than silently suppressed. Genuine filesystem write limitations are captured and reported.

### R2 — Hard caps and single effective deadline before execution
- **Hard caps**: Enforced `MAX_CALLS_CAP = 20` and `DEADLINE_CAP = 25.0`. Configuration values above these caps, or non-finite/negative/boolean configurations, are rejected with `ValueError` at initialization/entry.
- **Reduced budgets supported**: Smaller smoke budgets (e.g. `max_calls=1`, `deadline=0.55`) are fully supported.
- **Single effective budget**: Verified consistency between runner and `VisualPolicySession` adapter; budget disagreements (different `max_calls` or `deadline`) are explicitly rejected with `ValueError`.
- **Pre-execution duration check**: Proposed action durations are rounded up (`ceil(seconds / 0.001) * 0.001`) and checked against the captured simulation timestamp and deadline *before* invoking `session.execute`. If the action exceeds the remaining deadline time, it is rejected immediately with `Action exceeds episode deadline` without stepping physics or overshooting time.
- **CLI validation and seed-820 scope**: The CLI entrypoint validates all budget caps and argument types before simulator reset or rendering, and strictly restricts real simulation smoke runs to development seed 820 and fixed camera view. Held-out seeds 840–849 are strictly prohibited.
- **Provenance metadata**: Provenance records both protocol caps (`max_calls_cap: 20`, `deadline_cap_s: 25.0`) and actual configured limits (`configured_max_calls`, `configured_deadline_s`).

### Reproducer comparison (`004-repro.py`)
| Test case | Prior behavior (tip 8900642) | Updated behavior |
|---|---|---|
| `NaN response` | Crashed with `ValueError` in `write_json`; report lost | Returns `malformed_response`, calls: 1, time: 0.5s; report exists with diagnostic `NaN` representation |
| `Malformed response envelope` (`{'output': None}`) | Crashed with `TypeError` in parser; report lost | Returns `malformed_response`, calls: 1, time: 0.5s; report exists |
| `Execution exception` | Crashed with `RuntimeError` in loop; report lost | Returns `execution_exception`, calls: 1, time: 0.5s; report exists |
| `21 allowed calls` | Permitted 21 calls (exceeded cap) | Rejected with `ValueError` (capped at 20) |
| `Deadline overshoot` | Executed 1.0s action from t=0.5s past deadline 1.0s to t=1.5s | Pre-execution check rejects action; returns `rejected_action`, calls: 1, time: 0.5s (never overshoots) |
| `Boolean seconds` (`seconds: True`) | Accepted, converted to `1.0` | Rejected with `MalformedResponseError: seconds must be a finite float, got True` |

### Regression test suite expansion
- `tests/test_humanoid_visual_policy_runner.py`: expanded from 16 to 28 tests (all 28 pass in ~7.4s).
- Full repository test discovery: **173 tests passed in 143.970s** (0 failures, 0 errors).
- Historical smoke artifacts in `experiments/humanoid-pick-place/results/visual_policy_scaffold/` preserved unchanged.

## Codex integration disposition — 2026-09-13

Accepted with integration corrections after reviewing AGY tip `64c8907a39f8285c7e8fa2245a53454d1cc75474`.
See [004 acceptance](../reviews/004-acceptance.md) for residual execution-result
validation and unknown-outcome reporting fixes. The integrated full suite passes
175 tests; historical stub artifacts remain unchanged. This does not qualify a
live model or the temporal estimator.
