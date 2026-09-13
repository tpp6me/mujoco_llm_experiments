# AGY completion — task 005

Status: **ready for review**
Task brief: `coordination/agy/tasks/005-visual-provider-adapter.md`
Branch: `agy/005-visual-provider-adapter`
Starting commit: `bcdeadb0d02bdef9dd975742b23650c64a6de56b`
Implementation commit: `a4cae354778227ee48a1263cb984f0bf71120316`
Worktree: `/private/tmp/mujoco-llms-agy-005`

---

## Changes and rationale

Task 005 implements the multimodal OpenAI Responses wire-format adapter with an explicitly injected offline transport, prepares an unfrozen first visual LLM development pilot draft ([`experiments/humanoid-pick-place/protocols/V1_PROPOSAL.md`](../../experiments/humanoid-pick-place/protocols/V1_PROPOSAL.md)), provides a dry request-export command with a compact manifest, hardens envelope validation and failure classification, and validates offline boundary enforcement.

### 1. Multimodal provider adapter module (`humanoid_sim/visual_provider_adapter.py`)

- **Pure request builder (`build_responses_request`)**:
  - Translates provider-neutral `public_payload` into OpenAI Responses wire format.
  - Top-level fields: `model` (default `'gpt-5.6-sol'`), `store: false`, `reasoning: {"effort": "low"}`, `max_output_tokens: 2048`, `instructions: VISUAL_PROMPT`.
  - Structured output schema: `text.format` JSON schema (`name: 'humanoid_primitive'`, `strict: true`) using the canonical `action_schema()`.
  - Multimodal user message input:
    1. `input_text`: Serialized allowlisted JSON containing `instruction_version`, `remaining_time_s`, `remaining_actions`, `observation`, and `history`. Crucially, the raw base64 image string is **omitted** from this companion text JSON to eliminate duplicate token expansion and prevent prompt bloating.
    2. `input_image`: Data URL (`data:image/png;base64,...`) containing the original PNG bytes with explicitly recorded detail (`detail: high`).
  - Pre-transport validation: Strictly validates configuration, base64 encoding, PNG magic bytes (`\x89PNG\r\n\x1a\n`), and SHA-256 hash match before invoking transport.
  - Strict allowlist filtering: Completely strips any planted private fields (e.g. `secret_object_truth`, `score`, `private_scorer_report`, `task_state`, `private_oracle`) from observation, robot state, camera, and history.
  - Bounded history: Limits history to at most 20 preceding steps.

- **Strict envelope validation (`validate_response_envelope`)**:
  - Validates provider envelope structure before returning an action to the visual runner.
  - Requires `status == 'completed'`. Envelopes with `status: 'incomplete'`, `status: 'failed'`, or missing/invalid statuses raise `MalformedResponseError` immediately, ensuring an incomplete or failed envelope can **never** execute an apparently valid command nested inside it.
  - Refusal detection: Root-level `status: 'refusal'` or `refusal` fields, as well as message content items with `type: 'refusal'`, raise `ModelRefusalError`.
  - Tool output and message sanitization: Output items of type `tool_call`, `function_call`, `call`, or `tool_output`, multiple message items, or multiple `output_text` chunks raise `MalformedResponseError`.
  - Reasoning metadata handling: Items with `type: 'reasoning'` are cleanly ignored and never interpreted as commands.
  - Command validation: Parses `output_text` with `strict_json` (rejecting duplicate keys and non-finite constants) and reuses the runner's primitive validator to enforce workspace bounds, unit quaternion norm ($\pm 10^{-4}$), hand closure bounds, duration limits ($[0.02, 10.0]$ s), and boolean rejection.

- **Injected offline transport callable (`VisualProviderAdapter`)**:
  - Requires an explicit callable `transport` in its constructor. Omitting transport or passing `None` fails immediately (`ValueError`) without attempting credential lookup (`OPENAI_API_KEY`) or default HTTP client instantiation.
  - Separate attempt audit trail: When `record_dir` is configured, writes `provider_call_NNN.json` containing the exact request body, raw response, provider status, response ID, returned model, reported token usage, wall latency, image SHA-256, request SHA-256, and classified outcome.
  - Honest accounting: Call counts are tracked honestly; attempting to overwrite an existing record raises `ValueError`.
  - No dollar cost fabrication: Reported token usage is retained as reported; missing usage is marked `{"status": "unknown"}`. No dollar costs or invoice estimates are fabricated from offline fixtures.
  - Raw failure preservation: Raw responses are preserved in attempt records on failure, passing only a validated command or refusal outcome to the visual loop.

- **Dry request export CLI (`export_request`, `main`)**:
  - Standalone command to convert an archived public observation or payload into the exact Responses request body:
    ```sh
    .venv/bin/python -m humanoid_sim.visual_provider_adapter \
      --input experiments/humanoid-pick-place/results/visual_policy_scaffold/demo_request_payload.json \
      --output runtime/exported_request.json \
      --model gpt-5.6-sol \
      --manifest experiments/humanoid-pick-place/results/visual_provider_adapter/request_manifest.json
    ```
  - Requires explicit model configuration (`--model`).
  - Refuses to overwrite existing files.
  - Cannot send network requests (no transport or network client initialized).
  - Emits a compact request manifest ([`experiments/humanoid-pick-place/results/visual_provider_adapter/request_manifest.json`](../../experiments/humanoid-pick-place/results/visual_provider_adapter/request_manifest.json)) recording source provenance, SHA-256 hashes, image dimensions ($960 \times 720$), and field layout without storing another large duplicate base64 PNG in Git.

### 2. Visual policy runner enhancements (`humanoid_sim/visual_policy_runner.py`)

- **Envelope parser hardening (`parse_and_validate_response`)**:
  - When parsing dictionary responses containing an `'output'` list, requires `parsed.get('status') == 'completed'`.
  - Rejects unexpected tool output items and multiple action messages.
- **Specific exception handling (`run_visual_episode`)**:
  - Directly catches `ModelRefusalError` and `MalformedResponseError` when invoking `model_callable`, mapping them cleanly to `'refusal'` and `'malformed_response'` termination reasons without classifying them as generic unhandled exceptions.
  - Preserves Task 004 execution result timing validation, unknown movement accounting on execution exceptions (`execution_outcomes_unknown`), and evaluator error separation.
- **Source provenance tracking (`provenance`)**:
  - Adds `humanoid_sim/visual_provider_adapter.py` SHA-256 to provenance `source_sha256`.

### 3. Unfrozen first visual pilot proposal (`experiments/humanoid-pick-place/protocols/V1_PROPOSAL.md`)

- Proposes a concrete, unfrozen first visual LLM development pilot draft:
  - Single development seed 820 probe (held-out seeds 840–849 remain untouched).
  - Fixed camera view (`camera: fixed`, $960 \times 720$).
  - Public allowlist input condition: single monocular RGB image per step, proprioception, bounded history ($\le 20$ steps). Zero private truth, zero basket coordinates, zero oracle scorer access.
  - Paused inference timing: simulation physics is paused during model deliberation.
  - Hard budgets: 20-call maximum (`MAX_CALLS_CAP = 20`) and 25.0-second simulated deadline (`DEADLINE_CAP = 25.0`).
  - Model comparator: Reuses L2's model condition (`gpt-5.6-sol`, reasoning effort low, max output tokens 2048) to ensure comparability with exact-state results rather than silently changing models.
  - Strict stop rules: Immediate termination on refusal, malformed JSON, schema violation, envelope failure, tool output, transport error, collision guard rejection, or budget exhaustion. Zero silent retries or replacement commands.
  - Private post-hoc scoring: Evaluates lift, containment, placement, withdrawal, and penetration ($\le 2\text{ mm}$) strictly outside policy inputs.
  - Full failure denominators: Retains all attempts, refusals, timeouts, and errors in report denominators.
- Explicit uncompleted prerequisites for live execution:
  1. Live HTTP/TLS transport client implementation.
  2. Verified multimodal token spend reservation model (accounting for high-detail image tiles: $960 \times 720$ requires 4 tiles = 853 image tokens plus text tokens).
  3. Explicit total spend authorization and budget reservation from project coordinator.
  4. API access verification confirming provider account quota and model availability.
  5. Frozen source hashes (Git commit SHA, prompt SHA-256, schema SHA-256).
- Explicit disclaimers: Offline mocks are plumbing tests, not LLM capability evidence; zero movement after uncertain execution is never claimed without trustworthy post-execution state.

### 4. Comprehensive verification suite (`tests/test_visual_provider_adapter.py`)

- 19 focused tests covering:
  - Request builder image decoding, SHA-256 verification, and single image assertion.
  - Exclusion of base64 image from companion text JSON.
  - Exclusion of planted private fields across all payload levels.
  - History bounded to at most 20 preceding steps.
  - Pre-transport validation of malformed base64, corrupted PNG, hash mismatch, and configuration parameters.
  - Constructor failure when transport is omitted, without network or credential access.
  - Injected transport success with honest attempt logging (`provider_call_NNN.json`).
  - Reasoning metadata handling (ignored cleanly).
  - Refusal handling at envelope root and message content levels.
  - Incomplete and failed provider envelope status rejection (never executing nested commands).
  - Unexpected tool output and multiple message item rejection.
  - Malformed JSON, boolean arguments, out-of-bounds arguments, and non-unit quaternion rejection.
  - Transport exception handling and audit trail retention.
  - Unknown usage labeling without dollar cost fabrication.
  - Honest callback counters and refusal to overwrite existing records.
  - End-to-end `run_visual_episode` with adapter and fake transport (2 completed actions on seed 820).
  - End-to-end failure termination before execution on incomplete envelope.
  - Standalone dry export command and compact manifest creation.
  - Absolute network and credential isolation boundary checks.

### 5. Documentation and plan updates

- [`experiments/humanoid-pick-place/VISUAL_POLICY_RUNNER.md`](../../experiments/humanoid-pick-place/VISUAL_POLICY_RUNNER.md): Added Section 8 detailing the multimodal adapter wire format, envelope validation, injected transport, dry export, and readiness boundaries.
- [`experiments/humanoid-pick-place/PLAN.md`](../../experiments/humanoid-pick-place/PLAN.md): Checked off Task 005 under Next Actions.

---

## Validation

All checks were executed from `/private/tmp/mujoco-llms-agy-005` using the primary project virtual environment:
`/Users/praveen/work/github/mujoco-llms/.venv/bin/python`.

### 1. Focused visual policy runner and provider adapter suite

- **Command**:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest \
    tests/test_humanoid_visual_policy_runner.py \
    tests/test_visual_provider_adapter.py -v
  ```
- **Outcome**: **49 tests passed in 7.760 s** (30 runner tests + 19 adapter tests).
- **Retained Log**: [`coordination/agy/reports/005-focused-tests.log`](005-focused-tests.log).

### 2. Dry request export and manifest check

- **Command**:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.visual_provider_adapter \
    --input experiments/humanoid-pick-place/results/visual_policy_scaffold/demo_request_payload.json \
    --output /private/tmp/test_request_export.json \
    --model gpt-5.6-sol \
    --manifest experiments/humanoid-pick-place/results/visual_provider_adapter/request_manifest.json
  ```
- **Outcome**: Completed successfully with exit code 0. Validated compact manifest generation without network access or duplicate binary storage.

### 3. Full repository test discovery

- **Command**:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v
  ```
- **Outcome**: **194 tests passed in 146.911 s**. All 175 baseline tests and all 19 new adapter tests pass cleanly.
- **Retained Log**: [`coordination/agy/reports/005-full-discovery.log`](005-full-discovery.log).

---

## Experiment evidence

- **Scope and Environment**: Offline implementation and unit verification only. Development seed 820 used for plumbing checks; held-out seeds 840–849 strictly unrun.
- **Network and Credential Isolation**: Verified via explicit test assertions monkeypatching sockets and urllib, and confirming zero `OPENAI_API_KEY` access.
- **Denominators and Accounting**: All failure modes (refusals, incomplete envelopes, malformations, transport exceptions) are verified to increment errors/refusals and preserve raw evidence without retry or score contamination.
- **Artifacts Retained**:
  - `experiments/humanoid-pick-place/results/visual_provider_adapter/request_manifest.json`: Compact dry export manifest.
  - `experiments/humanoid-pick-place/protocols/V1_PROPOSAL.md`: Unfrozen pilot proposal.
  - `coordination/agy/reports/005-focused-tests.log`: Exact 49-test focused suite output.
  - `coordination/agy/reports/005-full-discovery.log`: Exact 194-test repository discovery output.

---

## Limitations and next checkpoint

1. **Adapter Readiness vs Live Execution**: The adapter wire-format and envelope validator are verified with offline injected transport only. Live execution remains blocked pending authorization of:
   - Live HTTP/TLS transport client.
   - Multimodal token spend reservation model.
   - Explicit total budget approval.
   - API quota and model availability verification.
   - Protocol freeze with source hashes.
2. **Perception and Pose Gate**: Carried-object pose remains unqualified; passive P5 development mean is 5.8715 mm against the unchanged 5.0 mm gate. The visual runner does not rely on unqualified carried-pose candidates.
3. **No Model Manipulation Claim**: No live model manipulation or task placement success is claimed.
