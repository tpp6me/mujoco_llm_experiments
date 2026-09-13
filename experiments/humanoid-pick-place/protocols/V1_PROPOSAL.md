# Proposed Successor Protocol V1 — First Visual LLM Development Pilot Draft

**STATUS: HISTORICAL PLANNING PROPOSAL — NOT FROZEN, NOT EXECUTED.**

**Superseded by user direction on 2026-09-13:** do not implement or run this OpenAI
API condition. Codex is the requested tool; see [current execution policy](../../../coordination/EXECUTION_POLICY.md).
A Codex-based controller requires its own declared execution condition.
*This proposal specifies the protocol for a future first live visual LLM manipulation trial under the humanoid experiment. No live API transport or spend is authorized or executed under AGY Task 005. Offline stubs and mocked fixture runs establish adapter and scaffolding readiness only; they do not demonstrate model manipulation performance, model availability, or actual cost.*

---

## 1. Objective and Scientific Scope

The objective of Protocol V1 is to evaluate whether a multimodal vision-language model, interacting through the accepted visual observation boundary and the guarded low-level robot interface, can select manipulation actions that pick a red block from a table and place it inside a basket in MuJoCo G1 simulation using camera RGB and robot proprioception.

### 1.1 Comparator Condition

To preserve continuity and comparability with the exact-state development pilot ([L2](L2.md)), this protocol retains the same model family, configuration, and interface conventions:
- **Model**: `gpt-5.6-sol` (via OpenAI Responses API wire format)
- **Reasoning Effort**: `low`
- **Output Token Limit**: 2048 (`max_output_tokens: 2048`)
- **Action Schema**: Strict JSON Schema Structured Output (`humanoid_primitive`)
- **System Prompt**: `VISUAL_PROMPT` (adapted from L2 exact-state prompt to specify RGB camera observations and exclude exact object/basket coordinate truth)

Reusing L2's model family and configuration preserves continuity with earlier exact-state exploration and avoids confounding observations with an unannounced model migration. It does not establish causal attribution between visual and exact-state conditions, as existing L2 trials and a single seed-820 pilot are not matched randomized trials.

### 1.2 Boundary Clarifications

- **Scaffolding vs Performance**: Offline tests, mock fixtures, and injected transport tests are plumbing verifications. They do not constitute model capability evidence or visual manipulation success.
- **Not a Matched Formal Benchmark**: This protocol specifies a single exploratory development pilot on seed 820. It is not a formal comparative benchmark across a wide population.
- **Held-Out Isolation**: Seeds 840–849 remain strictly reserved for later formal evaluation and are not run in this pilot.

---

## 2. Experimental Condition and Input Specification

### 2.1 Environmental Setup

- **Simulation**: Unitree G1 humanoid with hands, fixed pelvis, table, red block, and basket in MuJoCo.
- **Development Seed**: Seed 820 only.
- **Camera View**: Fixed external observer camera (`camera: fixed`), resolution $960 \times 720$, pinhole projection with known extrinsic rotation matrix and intrinsic focal/principal point calibration.
- **Temporal Mechanics**: Paused decision time. Physics is paused while the model computes. Only commanded action durations advance simulated time.

### 2.2 Public Observation Allowlist

Each decision step captures a single fresh visual observation. The model callable receives only:
1. **Camera Calibration**: Width ($960$), height ($720$), projection (`pinhole`), camera world position, rotation matrix ($R_{w\to c}$), focal lengths, principal points, axis conventions.
2. **Robot Proprioception**: Arm and hand joint names, positions ($\text{rad}$), velocities ($\text{rad}/\text{s}$), right hand grasp-site world position ($XYZ$), right hand quaternion ($WXYZ$), and active contact link names.
3. **Image Content**: Exactly one monocular RGB image per step, transmitted as an `input_image` data URL (`data:image/png;base64,...`) with detail explicitly recorded as `detail: high`. The base64 string is omitted from the companion text payload to avoid redundant token expansion.
4. **Image Provenance**: SHA-256 hash of the decoded PNG bytes (`rgb_sha256`), observation UUID (`observation_id`), and simulated capture timestamp (`time_s`).
5. **Budgets**: Remaining simulated time (`remaining_time_s`) and remaining action attempts (`remaining_actions`).
6. **Public History**: Sanitized sequence of up to 20 preceding action requests and their public execution responses (status, duration, updated robot proprioception).

### 2.3 Strict Exclusion of Private Truth

The payload strictly excludes:
- Ground-truth object coordinates or orientations.
- Ground-truth basket reference coordinates or floor boundaries.
- Oracle evaluator feedback, distance metrics, contact forces, or score reports.
- Private simulator objects, file paths, diagnostic fields, or conversation thread IDs.

---

## 3. Action Interface, Schema, and Hard Budgets

### 3.1 Primitives

The model selects exactly one primitive per turn from the allowlisted v2 action schema:
- `move`: `xyz_m` in world metres ($X \in [0.15, 0.55]$, $Y \in [-0.60, -0.05]$, $Z \in [0.60, 1.15]$), `quaternion_wxyz` (unit norm $\pm 10^{-4}$), `seconds` $\in [0.02, 10.0]$.
- `hand`: `closure` $\in [0.0, 1.0]$ ($0.0 = \text{open}$, $1.0 = \text{close}$), `seconds` $\in [0.02, 10.0]$.
- `hold`: `seconds` $\in [0.02, 10.0]$.

Numeric arguments reject boolean types (`True`/`False`), non-finite values (`NaN`, $\pm\infty$), and unrecognized extra keys.

### 3.2 Hard Pilot Budgets

- **Maximum Model Calls**: At most 20 actions per episode (`MAX_CALLS_CAP = 20`).
- **Simulated Deadline**: At most 25.0 simulated seconds per episode (`DEADLINE_CAP = 25.0`).
- **Duration Rounding**: Action duration is rounded up to millisecond physics steps ($\lceil \text{seconds} / 0.001 \rceil \times 0.001$). Actions that would cause simulated time to exceed the 25.0 s deadline are rejected before execution without advancing physics.

---

## 4. Stopping Rules and Full Failure Denominators

### 4.1 Termination Criteria

An episode terminates immediately upon any of the following conditions:
1. **Model Refusal**: Model envelope or message content indicates a refusal.
2. **Malformed Response**: JSON parse error, non-finite constant, duplicate key, missing command wrapper, invalid primitive action, missing argument, out-of-bounds argument, boolean argument, or non-unit quaternion.
3. **Envelope Error**: Provider envelope status is not `completed` (e.g. `incomplete`, `failed`, `cancelled`), contains unexpected tool outputs, or contains multiple action messages.
4. **Transport Error**: Network timeout, connection failure, HTTP error status, or transport exception.
5. **Interface Guard Rejection**: Commanded pose fails kinematic reachability or preflight collision safeguard (trajectory penetration $> 2\text{ mm}$ against environment geometry).
6. **Observation Expiry**: Attempting to execute an action against a stale or already consumed `observation_id`.
7. **Budget Exhaustion**: Reaching 20 model calls or reaching 25.0 simulated seconds.

Termination is governed strictly by public control, error, interface safeguard, and budget limits. The visual runner does not consult private evaluator task success during the loop; task success is scored strictly post-hoc (Section 5).

### 4.2 Zero Retries and Denial of Hidden Recovery

- No silent retries, prompt revisions, JSON repair routines, replacement commands, or fallback controllers are permitted within an episode.
- Every model call, refusal, schema rejection, interface rejection, and timeout is retained in the complete denominator.
- A failed attempt must never be presumed to have caused zero physical movement if execution was in flight when failure occurred; in such cases, `execution_outcomes_unknown` is incremented and final time is marked unknown unless post-execution state is authoritatively confirmed.

---

## 5. Private Scoring and Post-Hoc Evaluation

Task scoring is conducted post-hoc via the simulation evaluator (`env.scorer.report()`) and written to a separate `evaluator_report.json`. The evaluator measures:
1. **Lift**: Red block lifted at least $0.04\text{ m}$ above the table with continuous hand contact for $\ge 0.2\text{ s}$.
2. **Containment**: Block fully contained within the horizontal rim bounds of the basket.
3. **Placement**: Block resting on the basket floor ($Z \approx 0.712\text{ m}$), without hand contact, nearly stationary for $\ge 2.0\text{ s}$.
4. **Withdrawal**: Hand withdrawn at least $0.12\text{ m}$ from the block after release.
5. **Mechanical Safety**: Maximum object penetration $\le 2.0\text{ mm}$ throughout the trajectory.

---

## 6. Uncompleted Prerequisites for Live Execution

Before Protocol V1 can be frozen or executed with live network calls and provider spend, the following concrete prerequisites must be completed and reviewed:

- [ ] **Live HTTP/TLS Transport**: Implement an isolated, auditable HTTPS transport client utilizing standard secure libraries, explicit timeouts, and strict error translation.
- [ ] **Multimodal Spend Reservation Model**: Adapt the L2 token reservation logic for multimodal inputs. Under current official OpenAI guidance ([Images and vision, checked 2026-09-13](https://developers.openai.com/api/docs/guides/images-vision)), vision token calculations for `gpt-5.6-sol` use 32-pixel patches with a 1.2 multiplier ($\lceil 30 \times 23 \times 1.2 \rceil = 828$ estimated image tokens for an unresized $960 \times 720$ image at `detail: high`, within the 2,500-patch limit). This provides an image token estimate, not a complete request reservation or invoice guarantee. Text, history, structured schema, and output token costs and uncertainties must be bounded and reserved in the later spend task before initiating any call.
- [ ] **Explicit Total Spend Approval**: Obtain explicit budget authorization from the project owner before executing live paid API requests.
- [ ] **API Access Verification**: Verify provider account access, quota tier, and model availability for `gpt-5.6-sol` using an approved, verified method without embedding secrets in repo code and without making unverified assumptions about zero-cost preflight endpoints.
- [ ] **Protocol Freeze and Source Hashes**: Record exact Git commit SHA, prompt SHA-256, and schema SHA-256 in a frozen `V1.md` protocol document.

---

## 7. Artifacts and Audit Trail

A completed V1 episode must preserve:
- `call_NNN.json`: Public request payload, raw response envelope, parsed command, wall latency, and interface response.
- `adapter/provider_call_NNN.json`: Wire-format request body, provider envelope, status, usage, response ID, request SHA-256, and image SHA-256.
- `report.json`: Overall summary with controller name, seed, termination reason, completed actions, refusals, errors, simulation time, wall latency, and `placement_success_claimed: false`.
- `evaluator_report.json`: Post-hoc scoring metrics retained strictly outside policy inputs.
- `episode.npz`, `metadata.json`, `events.json`: Authoritative physical simulation state.
