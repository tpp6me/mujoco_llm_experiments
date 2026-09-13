# Offline RGB-to-action visual policy runner

Date: 2026-09-13.
Status: **Scaffolding and offline verification complete (Task 004)**.
Branch: `agy/004-visual-policy-scaffold`.

This document specifies the provider-neutral offline RGB-to-action policy loop.
It connects the visual observation boundary (`VisualSession`) to an injected policy
callable, strictly isolates policy inputs through a public allowlist, enforces fresh
observation capture and guarded action execution, and logs reviewable artifacts.

> [!IMPORTANT]
> **Scaffolding, not an experiment or success claim**: This module is test infrastructure.
> No live LLM or VLA model has been invoked, no provider credentials or HTTP transport
> are enabled, and no visual manipulation success is claimed. Scripted test stubs exercise
> plumbing only and must never be treated as conventional comparators or learned policies.
> Carried-object pose remains unqualified (passive P5 development mean is 5.8715 mm against
> an unchanged 5.0 mm gate); the visual runner does not rely on temporal pose candidates,
> private object truth, or oracle scorer feedback.

---

## 1. Architectural separation

The visual runner strictly distinguishes three categories:

| Category | Definition | Included in Task 004? |
|---|---|---|
| **Implementation** | Python module `humanoid_sim/visual_policy_runner.py`, narrow session adapter, allowlist builders, response validators, and unit tests | Yes |
| **Simulation smoke check** | Deterministic local run with named scripted stub on development seed 820 to verify log structure and state persistence | Yes (retained offline demo) |
| **Model evidence** | Scored manipulation trials driven by a live vision-language-action model | **No** (future frozen pilot) |

The runner preserves the exact-state L2 runner (`humanoid_sim/llm_runner.py`), provider client,
and historical mechanical evidence unchanged.

---

## 2. Public request contract

The model callable receives a single provider-neutral dictionary constructed strictly
from an **allowlist**. No environment instance, simulator state, task ground truth,
object coordinate, private scorer, or diagnostic object is ever serialized or accessible.

### 2.1 Allowlist specification

```json
{
  "instruction": "<VISUAL_PROMPT string>",
  "instruction_version": 1,
  "action_schema": { ... },
  "remaining_time_s": 24.5,
  "remaining_actions": 20,
  "observation": {
    "schema_version": "humanoid-visual-v1",
    "observation_id": "918f43c2a91645af88bdc504a2ba692e",
    "time_s": 0.5,
    "camera": {
      "width": 960,
      "height": 720,
      "projection": "pinhole",
      "camera_world_xyz_m": [0.24, -0.81, 2.02],
      "world_to_camera_rotation": [[...], [...], [...]],
      "focal_xy_px": [869.12, 869.12],
      "principal_xy_px": [479.5, 359.5],
      "axes": "camera X right, Y down, Z forward; world Z up; pixel centers indexed from 0"
    },
    "robot_state": {
      "schema_version": "humanoid-actions-v2",
      "instruction_version": 1,
      "mode": "robot_state",
      "time_s": 0.5,
      "frame": "world",
      "supported_body": true,
      "robot": {
        "joint_names": [ ... ],
        "joint_position_rad": [ ... ],
        "joint_velocity_rad_s": [ ... ],
        "hand_xyz_m": [0.2385, -0.1803, 0.9332],
        "hand_quaternion_wxyz": [0.4925, -0.4933, 0.5070, 0.5070],
        "contact_links": []
      }
    },
    "rgb_png_base64": "<base64 encoded 960x720 PNG>",
    "rgb_sha256": "c59315cbd6cc656d0f86ba918ede532855377a7eff1c9da0e4a8252034c3ce65"
  },
  "history": [
    {
      "action": {
        "action": "hold",
        "arguments": {"seconds": 0.5},
        "request_id": "visual-1"
      },
      "response": {
        "request_id": "visual-1",
        "status": "completed",
        "start_time_s": 0.5,
        "end_time_s": 1.0,
        "robot_state": { ... }
      }
    }
  ]
}
```

### 2.2 Instruction prompt

The visual prompt (`VISUAL_PROMPT`) replaces L2's exact-state prompt:
- States that the policy receives **visual observations (RGB image from camera)** and **robot proprioception**.
- Explicitly notes: *No ground-truth object coordinates, basket coordinates, or oracle score feedback are provided.*
- Removes L2's text stating that no images are supplied and removes exact basket reference coordinate claims.
- Preserves identical robot capabilities, workspace boundaries ($X \in [0.15, 0.55]$, $Y \in [-0.60, -0.05]$, $Z \in [0.60, 1.15]$), primitive definitions (`move`, `hand`, `hold`), downward hand orientation $[0.5, -0.5, 0.5, 0.5]$, duration limits ($[0.02, 10.0]$ s), and physical settling requirements.

### 2.3 Bounded history and isolation guarantees

- Prior action requests and execution outcomes are sanitized through allowlists before addition to history.
- Planted private fields (e.g. `task_state`, `score`, `secret_object_truth`, `private_diagnostics`) are stripped at the allowlist boundary and never reach the callable.
- History is bounded to at most 20 preceding steps.

---

## 3. Fresh observation and guarded execution loop

Each decision iteration enforces authoritative simulation freshness within a guaranteed whole-episode lifecycle:

1. **Whole-episode failure accounting**: Observation capture, validation, payload building, model execution, response parsing, pre-execution duration checking, interface execution, and outcome sanitization run inside a protected `try ... finally` block. A final `report.json` is guaranteed to be written upon any termination condition (including exceptions and malformations) with accurate stage-specific reasons and attempt counters.
2. **Pre-capture budget check**: Checks whether action call limit (at most 20) or simulation deadline (at most 25.0 s) is reached.
3. **Fresh capture and observation validation**: Calls `session.capture()` via `VisualPolicySession` adapter. Generates an opaque UUID `observation_id` and records the integration-state hash before and after capture. Observation fields, PNG bytes, and image SHA-256 hashes are strictly pre-validated.
4. **Allowlist payload construction**: Assembles the sanitized public contract payload.
5. **Timed stub invocation**: Calls the injected `model_callable`. Wall-clock latency is measured using an injectable clock (`clock()`), completely separate from simulated time.
6. **Strict parsing, boolean rejection, and diagnostic preservation**: Parses response JSON (rejecting duplicates and non-finite constants), normalizes provider-style envelopes, checks for model refusal, extracts primitive commands, and strictly validates types. Numeric command fields strictly reject boolean values (`True`/`False`). Invalid or non-finite raw responses are preserved in log files via an explicit JSON-safe diagnostic format (`{"__diagnostic_nonfinite__": "NaN"}`) without raising serialization errors or emitting invalid JSON.
7. **Pre-execution duration check**: Before invoking execution, the proposed action duration is rounded up to millisecond physics increments (`ceil(seconds / 0.001) * 0.001`) and checked against the captured observation time and episode deadline. Actions that would overshoot the deadline are rejected immediately without executing or stepping physics.
8. **Guarded execution**: Submits valid commands through `VisualSession.execute(observation_id, request)`.
   - **Single-use constraint**: The observation ID is consumed upon first execution attempt. Any subsequent attempt with the same ID is rejected with `Stale or unknown visual observation` without advancing physics.
   - **Collision preflight**: Kinematic collision safeguard checks the commanded arm trajectory against environment geometry; penetrations $>2$ mm are rejected before physical stepping.
9. **No silent retries**: Any refusal, malformed response, unhandled exception, or interface rejection terminates the episode immediately without retries, replacement commands, or oracle fallback.

---

## 4. Pilot limits and timing

- **Protocol hard caps**: At most 20 actions (`MAX_CALLS_CAP = 20`) and 25.0 simulated seconds (`DEADLINE_CAP = 25.0`) per episode. Values exceeding these caps or invalid configurations (non-integer, non-finite, negative, boolean) are rejected at configuration time.
- **Single effective budget**: The runner and session adapter enforce one consistent budget; configuration disagreements between runner and adapter are rejected immediately.
- **Reduced smoke budgets**: Reduced limits (e.g. `max_calls=1`, `deadline=0.55`) are fully supported for fast regression testing.
- **Simulated deadline**: Durations undergo millisecond rounding (`ceil(seconds / 0.001) * 0.001`); requests exceeding the remaining time are rejected before execution.
- **Paused decision time**: Simulation physics pauses while the model callable computes. Action durations consume simulated time; model wall latency is recorded separately.
- **Injectable clocks**: Tests inject mock clocks (`MockClock`) to verify latency tracking without real-time delays or sleeping.

---

## 5. Offline named stubs

The runner provides built-in named stubs for development and testing:

| Stub name | Class | Behavior |
|---|---|---|
| `scripted` | `ScriptedDemoStub` | Deterministic 4-step sequence (hold $\to$ approach move $\to$ partial hand closure $\to$ hold) for plumbing verification |
| `hold` | `HoldStub` | Command sequence of explicit `hold` primitives |
| `refusal` | `RefusalStub` | Returns explicit refusal object; verifies refusal termination |
| `malformed` | `MalformedStub` | Returns invalid JSON / non-existent action; verifies schema rejection |
| `exception` | `ExceptionStub` | Raises `RuntimeError`; verifies transport exception handling |
| `collision` | `CollisionStub` | Targets table-penetrating pose ($Z=0.70$ m); verifies collision guard rejection |

---

## 6. Run instructions and artifacts

### 6.1 CLI invocation

Run the offline visual policy runner using the primary project virtual environment:

```sh
/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.visual_policy_runner \
  --output runtime/humanoid/visual-policy-new-smoke \
  --seed 820 \
  --stub scripted \
  --max-calls 4
```

> [!CAUTION]
> **Scope and seed protection**: Task 004 real simulation smoke checks are restricted strictly to authorized development seed 820 with fixed camera view. Seeds 840–849 are strictly reserved for held-out validation. The CLI validates all configuration and budget caps before simulator reset or rendering.

### 6.2 Retained artifacts

Each run directory contains:
- `call_NNN.json`: Step-by-step audit trail containing `observation_id`, `time_s`, `image_sha256`, full allowlisted `request`, `raw_response` (with JSON-safe diagnostic representation for non-finite values if needed), `command`, `wall_latency_s`, `interface_request`, and `interface_response`.
- `report.json`: Overall episode summary with controller name, seed, termination reason, error status, call/action counts, simulated time, total wall latency, image identity sequence, provenance hashes, and `placement_success_claimed: false`. Provenance records both protocol hard caps (`max_calls_cap: 20`, `deadline_cap_s: 25.0`) and actual configured limits (`configured_max_calls`, `configured_deadline_s`).
- `evaluator_report.json`: Post-hoc simulator scorer report (`env.scorer.report()`), retained **separately** from the policy log and never returned to policy history. Evaluator exceptions are reported under `evaluator_error` in `report.json` rather than silently suppressed.
- `episode.npz`, `metadata.json`, `events.json`: Full physical simulation state and events.

---

## 7. Work required for live adapter and frozen pilot

To advance from this offline scaffolding to a scored visual LLM pilot:

1. **Provider adapter**: Build a transport adapter that translates the provider-neutral `public_payload` into vendor-specific multimodal API formats:
   - OpenAI Responses API: multimodal message with base64 image input and JSON schema output.
   - Anthropic Messages API: image block with base64 data and tool use.
   - Google Gemini API: inline_data with image MIME type.
2. **Credential and network isolation**: Secure credential handling via environment variables; ensure dry-run/offline flags prevent accidental network access.
3. **Cost accounting and token reservations**: Adapt `Client` cost tracking to multimodal image token rates (e.g. OpenAI tile tokens, Gemini image pricing).
4. **Frozen protocol specification**: Author and freeze a protocol document defining:
   - Evaluated seeds (development seeds 820–829; no held-out seeds 840–849 until formal evaluation).
   - Fixed model identifier, system prompt hash, temperature/sampling parameters.
   - Maximum budget cap and token limits.
5. **Matched conventional vision comparator**: Build an equivalent conventional vision baseline before evaluating LLM visual manipulation claims.

## Integration review clarification

The committed `results/visual_policy_scaffold/` run remains historical evidence from
the original Task 004 implementation. It was not regenerated after review fixes;
its provenance does not include the subsequently added configured budget fields.
Use a new output directory for any later authorized smoke run.

Execution result timestamps are validated before counting completed actions.
Malformed results and execution exceptions stop after one attempt and increment
`execution_outcomes_unknown`: an attempt may have moved before failing. The final
simulation time is null when no trustworthy post-execution state is available.
Stale-observation rejections retain their original rejection classification.
Archive errors remain visible separately in `evaluator_error`.

---

## 8. Multimodal Responses provider adapter (Task 005)

Implemented in `humanoid_sim/visual_provider_adapter.py`, this adapter connects the
accepted visual policy loop to the OpenAI Responses wire format using an explicitly
injected offline transport.

### 8.1 Wire request construction (`build_responses_request`)

The pure request builder converts the sanitized `public_payload` into the Responses format:
- **Top-level parameters**: `model` (`gpt-5.6-sol`), `store: false`, `reasoning: {"effort": "low"}`, `max_output_tokens: 2048`, `instructions: VISUAL_PROMPT`.
- **Structured output**: `text.format` JSON schema (`humanoid_primitive`) using `action_schema()`, enforcing strict schema validation.
- **Multimodal input message**: Exactly one user message with two content items:
  1. `input_text`: JSON string containing public metadata (`instruction_version`, `remaining_time_s`, `remaining_actions`, `observation`, `history`). Crucially, the base64 image string is **omitted** from this text JSON to avoid redundant token billing and payload expansion.
  2. `input_image`: Data URL (`data:image/png;base64,...`) containing the original PNG bytes with explicitly recorded detail (`detail: high`).
- **Pre-transport validation**: Validates configuration, PNG magic bytes (`\x89PNG\r\n\x1a\n`), and SHA-256 hash match before invoking transport. Corrupted base64 or mismatched hashes fail immediately without network or transport involvement.

### 8.2 Strict envelope validation (`validate_response_envelope`)

Before returning an action to the visual runner, the adapter verifies the response envelope:
- **Envelope status**: Must be `completed`. Incomplete (`status: "incomplete"`), failed (`status: "failed"`), or unrecognized envelope statuses raise `MalformedResponseError` immediately, ensuring an incomplete envelope can **never** execute an apparently valid command nested inside it.
- **Refusal handling**: Explicit refusals at the envelope root or inside message content raise `ModelRefusalError`.
- **Tool and content sanitization**: Tool calls (`tool_call`, `function_call`, `call`), unexpected content types, multiple action messages, or multiple `output_text` chunks raise `MalformedResponseError`.
- **Reasoning metadata**: Reasoning items (`type: "reasoning"`) are cleanly ignored and never interpreted as commands.
- **Command validation**: Output text is parsed with `strict_json` (rejecting duplicates and non-finite numbers) and validated with the runner's primitive validator (`move` bounds, unit quaternion norm, `hand` closure, duration limits, boolean rejection).

### 8.3 Injected transport and attempt logging (`VisualProviderAdapter`)

- **No network or credentials**: Omitting the transport callable fails immediately (`ValueError`) without attempting credential lookup or default HTTP client instantiation.
- **Separate attempt records**: When `record_dir` is configured, each call writes `provider_call_NNN.json` containing the wire request, raw response, provider status, response ID, returned model, reported token usage, wall latency, and classified outcome.
- **Honest accounting and no overwrites**: Callback call counts are maintained honestly; attempting to overwrite an existing record raises `ValueError`.
- **No dollar cost fabrication**: Reported token usage is retained as reported. If missing, usage is marked `{"status": "unknown"}`. No dollar costs or invoice amounts are fabricated from offline fixtures.
- **Raw failure preservation**: Raw responses are preserved in the attempt records on failures, passing only a validated command or refusal outcome to the visual loop.

### 8.4 Dry request export CLI

The module provides a standalone dry-export command:
```sh
.venv/bin/python -m humanoid_sim.visual_provider_adapter \
  --input experiments/humanoid-pick-place/results/visual_policy_scaffold/demo_request_payload.json \
  --output runtime/exported_request.json \
  --model gpt-5.6-sol \
  --manifest experiments/humanoid-pick-place/results/visual_provider_adapter/request_manifest.json
```
The command requires explicit model configuration, refuses to overwrite existing files, cannot send network requests, and emits a compact manifest (`request_manifest.json`) recording source, hashes, image dimensions, and field layout without duplicating large base64 PNG strings in Git.

### 8.5 Status: Adapter readiness vs live execution

Task 005 establishes **adapter wire-format readiness** with offline transport. It does **not** authorize or execute live model trials. An unfrozen development pilot draft is specified in [protocols/V1_PROPOSAL.md](protocols/V1_PROPOSAL.md). Live execution requires subsequent authorization and completion of live HTTP transport, multimodal token spend reservations, total spend approval, and frozen source snapshots.
