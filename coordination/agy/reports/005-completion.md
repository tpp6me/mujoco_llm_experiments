# AGY completion — task 005

Status: **ready for review**
Task brief: `coordination/agy/tasks/005-visual-provider-adapter.md`
Branch: `agy/005-visual-provider-adapter`
Starting commit (task base): `bcdeadb0d02bdef9dd975742b23650c64a6de56b`
Amended initial local snapshot: `a4cae354778227ee48a1263cb984f0bf71120316` (amended locally, not an ancestor of pushed branch)
Reviewed tip (changes requested): `ea09ce7dc4a7fd1e091465fbb0912c26ff7ac613`
Worktree: `/private/tmp/mujoco-llms-agy-005`

---

## Changes and rationale

This revision addresses all findings from Codex review `coordination/agy/reviews/005-review.md` (R1, R2, R3), implementing complete adapter lifecycle failure retention, pre-transport pending records, honest callback accounting, full image raster decoding, distinct export destinations, explicit model configuration without implicit defaults, and protocol draft alignment.

### 1. R1 (High) — Retain attempts across complete adapter lifecycle and honest accounting

- **Separated invocation attempts from actual transport calls**:
  - `VisualProviderAdapter` now maintains separate counters: `invocation_count` (all preparation and preflight attempts) and `transport_call_count` (actual wire transport invocations).
  - The `call_count` property explicitly exposes `transport_call_count`, ensuring callback accounting truthfully reflects whether transport was called.
- **Pre-transport pending record persistence**:
  - When `record_dir` is configured, `VisualProviderAdapter` persists a pending attempt record (`status: "pending"`, `transport_invoked: false`, full serialized wire request body, image SHA-256, and request SHA-256) to `provider_call_NNN.json` **before** invoking transport.
  - If writing the initial pending record fails (e.g. filesystem permissions, directory path conflicts), transport is **never** invoked (`transport_call_count` remains 0).
- **Preflight preparation error retention**:
  - If request building fails during preflight (e.g. malformed base64, corrupted image raster data, hash mismatch, invalid arguments), a preparation record (`status: "preparation_error"`, `call: 0`, `transport_invoked: false`) is written to `provider_call_NNN.json`. Transport is never invoked (`call_count == 0`), and the exception is re-raised.
- **Unified failure-accounting boundary for metadata extraction and envelope validation**:
  - Metadata extraction (`id`, `status`, `usage`, `model`) and envelope validation (`validate_response_envelope`) are enclosed in the same protected `try...except` boundary.
  - Empty tuples (`()`), empty lists (`[]`), and non-dict scalars returned by transport are caught within this boundary. Raw response evidence is retained in `provider_call_NNN.json` with `status: "malformed_envelope"` before raising a controlled `MalformedResponseError`.
  - Never retries or attempts hidden repairs.
- **Interruption and exception preservation**:
  - Transport exceptions update the pending record to `status: "transport_exception"`, retain wall latency, and re-raise without swallowing errors.
  - Token usage is recorded as reported, or marked `{"status": "unknown"}` without dollar cost fabrication.

### 2. R2 (Medium) — Full image raster validation, distinct export destinations, and explicit model configuration

- **Full PNG decoding and verification (`validate_png_base64`)**:
  - Updated `validate_png_base64` to force full decompression and raster chunk decoding with `img.load()`.
  - Rejects truncated or corrupted pixel data (e.g. valid PNG header with truncated IDAT data) with `ValueError: Corrupted or truncated PNG image data: ...`, even if the caller computed SHA-256 over those truncated bytes.
- **Distinct resolved path validation in export utility (`export_request`)**:
  - Resolves `output_path` and `manifest_path` to canonical paths before performing any filesystem writes.
  - Rejects equal or resolved-alias output and manifest paths (`ValueError: Output path and manifest path must be distinct`) before creating or writing either file.
  - Preserves source files and refuses to overwrite existing files (`FileExistsError`).
- **Explicit model configuration across all entrypoints**:
  - Removed all implicit model defaults across the public API.
  - `build_responses_request`, `VisualProviderAdapter`, and `export_request` strictly require an explicit, non-empty `model` string (raising `TypeError` if omitted, and `ValueError` if empty or whitespace).
  - Updated CLI parser in `humanoid_sim/visual_provider_adapter.py` to require `--model`.
  - Updated all documentation examples and test fixtures to pass explicit models (`model='gpt-5.6-sol'` or `'offline-fixture-model'`).
  - Updated dry export CLI documentation to target fresh runtime destinations (`runtime/humanoid/visual-provider-export/...`) rather than overwriting committed repo manifests.

### 3. R3 (Medium) — Pilot draft consistency and scientific boundaries (`V1_PROPOSAL.md` & `PLAN.md`)

- **Removed private evaluator task success from loop stopping rules**:
  - In `experiments/humanoid-pick-place/protocols/V1_PROPOSAL.md`, Section 4.1, removed item 8 (private evaluator task success).
  - Clarified that the visual runner stops strictly on public control, error, interface safeguard, and budget conditions, while task success is evaluated strictly post-hoc (Section 5).
- **Corrected causal attribution claims**:
  - In `V1_PROPOSAL.md`, Section 1.1, retained the continuity claim (reusing L2's model family and configuration avoids confounding with an unannounced model migration), while explicitly removing causal attribution claims, noting that existing L2 trials and a single seed-820 pilot are not matched randomized trials.
- **Updated image token calculations to official guidance**:
  - In `V1_PROPOSAL.md`, Section 6, removed the unsupported 853-image-token/four-tile assumption and unmeasured text token assumptions.
  - Documented current official OpenAI guidance ([Images and vision, checked 2026-09-13](https://developers.openai.com/api/docs/guides/images-vision)) using 32-pixel patches and 1.2 multiplier: $\lceil 30 \times 23 \times 1.2 \rceil = 828$ estimated image tokens for unresized $960 \times 720$ at `detail: high` (within the 2,500-patch limit).
  - Left live token spend reservation unimplemented for the dedicated future spend task and linked official documentation.
- **Removed zero-cost preflight assumption**:
  - In `V1_PROPOSAL.md`, Section 6, removed promises of a zero-cost preflight endpoint; noted that provider account access and model availability verification require an approved, verified method.
- **Preserved unchecked plan status**:
  - In `experiments/humanoid-pick-place/PLAN.md`, kept Task 005 `[ ]` unchecked pending review acceptance of a specific tip.

---

## Validation

All checks were executed from `/private/tmp/mujoco-llms-agy-005` using the primary project virtual environment:
`/Users/praveen/work/github/mujoco-llms/.venv/bin/python`.

### 1. Codex reproduction script verification

- **Command**:
  ```sh
  PYTHONPATH=. /Users/praveen/work/github/mujoco-llms/.venv/bin/python \
    /Users/praveen/work/github/mujoco-llms/coordination/agy/reviews/005-repro.py
  ```
- **Verified Behaviors**:
  - `pending record exists during transport: True` (R1 verified)
  - `empty tuple: MalformedResponseError record exists: True` (R1 verified)
  - `bad PNG: ValueError call_count: 0 actual callbacks: 0 records: [PosixPath('.../provider_call_001.json')]` (R1 verified)
  - `truncated PNG rejected: ValueError` (R2 full raster verification verified)
  - Same output/manifest path raises `ValueError` before either file is created (R2 verified)
  - Omitted `model` raises `TypeError` (R2 verified)

### 2. Focused visual runner and adapter suite

- **Command**:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest \
    tests/test_humanoid_visual_policy_runner.py \
    tests/test_visual_provider_adapter.py -v
  ```
- **Outcome**: **56 tests passed in 7.560 s** (30 runner tests + 26 adapter tests).
- **Retained Log**: [`coordination/agy/reports/005-focused-tests.log`](005-focused-tests.log).

### 3. Dry request export and manifest check

- **Command**:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.visual_provider_adapter \
    --input experiments/humanoid-pick-place/results/visual_policy_scaffold/demo_request_payload.json \
    --output /private/tmp/test_fresh_export_req.json \
    --model gpt-5.6-sol \
    --manifest /private/tmp/test_fresh_export_manifest.json
  ```
- **Outcome**: Completed successfully with exit code 0. Validated compact manifest generation without network access or duplicate binary storage, matching committed hashes.

### 4. Full repository test discovery

- **Command**:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v
  ```
- **Outcome**: **201 tests passed in 147.020 s**. All 175 baseline tests and all 26 adapter tests pass cleanly.
- **Retained Log**: [`coordination/agy/reports/005-full-discovery.log`](005-full-discovery.log).

---

## Experiment evidence

- **Scope and Environment**: Offline implementation and unit verification only. Development seed 820 used for plumbing checks; held-out seeds 840–849 strictly unrun.
- **Network and Credential Isolation**: Verified via explicit test assertions monkeypatching sockets and urllib, and confirming zero `OPENAI_API_KEY` access.
- **Denominators and Accounting**: All failure modes (refusals, incomplete envelopes, malformations, transport exceptions, preflight errors) are verified to increment errors/refusals and preserve raw evidence without retry or score contamination.
- **Artifacts Retained**:
  - `experiments/humanoid-pick-place/results/visual_provider_adapter/request_manifest.json`: Compact dry export manifest.
  - `experiments/humanoid-pick-place/protocols/V1_PROPOSAL.md`: Unfrozen pilot proposal.
  - `coordination/agy/reports/005-focused-tests.log`: Exact 56-test focused suite output.
  - `coordination/agy/reports/005-full-discovery.log`: Full repository discovery output.

---

## Limitations and next checkpoint

1. **Adapter Readiness vs Live Execution**: The adapter wire-format and envelope validator are verified with offline injected transport only. Live execution remains blocked pending authorization of:
   - Live HTTP/TLS transport client.
   - Multimodal token spend reservation model (accounting for 828 estimated image tokens for $960 \times 720$ at `detail: high` plus text/history/output tokens).
   - Explicit total budget approval.
   - API quota and model availability verification via an approved method.
   - Protocol freeze with source hashes.
2. **Perception and Pose Gate**: Carried-object pose remains unqualified; passive P5 development mean is 5.8715 mm against the unchanged 5.0 mm gate. The visual runner does not rely on unqualified carried-pose candidates.
3. **No Model Manipulation Claim**: No live model manipulation or task placement success is claimed.

## Codex integration disposition — 2026-09-13

Reviewed revision: `12da6162a4d9046d36d79ee8eaea2de304a68a18`.
Accepted with integration corrections; see [acceptance](../reviews/005-acceptance.md).
Codex tightened ambiguous transport-container rejection, preserved unknown dispatch
state for pending attempts and recorded caught interrupts in both adapter and episode
logs. The production offline adapter remains disconnected from HTTP transport.
The original dry-export manifest is unchanged. No paid pilot is qualified or run.
