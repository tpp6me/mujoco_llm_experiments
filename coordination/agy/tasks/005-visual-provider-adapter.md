# AGY task 005 — Multimodal provider adapter and pilot draft

Status: **ready**. Branch: `agy/005-visual-provider-adapter`.
Use `/private/tmp/mujoco-llms-agy-005`, starting from the main integration containing
this brief and Task 004 acceptance. Record its exact starting commit.

Read `coordination/agy/WORKFLOW.md`, `reviews/004-acceptance.md`, the experiment
`PLAN.md`, `VISUAL_POLICY_RUNNER.md`, and `humanoid_sim/visual_policy_runner.py`,
`visual.py`, `llm_runner.py` and their relevant tests.

## Objective

Make the accepted visual loop ready to speak the OpenAI Responses wire format,
using an explicitly injected offline transport. Preserve RGB as an actual image
content item and the single guarded primitive as structured output. Produce a
concrete first live-pilot draft for review. This task executes no paid requests and
does not demonstrate model manipulation performance.

Use this provider first because the existing exact-state L2 comparison already
uses it. Do not migrate models or add multiple providers. The adapter must accept
an explicit model identifier; offline fixtures do not establish model availability.

## Authorized scope

- Edit, test, commit and push only the dedicated task branch. Do not merge/push main.
- Reuse existing dependencies and the primary `.venv/bin/python` interpreter.
- Read official API documentation and existing public development observations.
  No credential lookup, API key access, default HTTP client, provider request,
  account/model listing call, SDK installation, hardware or dependency changes.
- No fresh episode generation is needed. Use existing seed-820 public observations,
  mock transport and mock renderer/session; if an existing test resets seed 820,
  that existing regression is allowed. Do not run rendering demos or optimizers.
- Preserve all existing artifacts, L2 behavior, scene/physics/camera/controller,
  temporal estimators and gates. Held-out seeds 840–849 remain unrun. P5 mean gate
  remains unmet (5.8715 mm versus 5.0 mm); do not relax or freeze it.

## Implementation checklist

- [ ] Add a small separate adapter module with a pure public-payload-to-request
  builder and a callable that requires an injected transport. Omitting transport
  must fail without reading credentials or constructing a network client.
- [ ] Build a Responses request with `store: false`, explicit model/output limit,
  current instruction, one user message containing allowlisted JSON text and one
  `input_image` data URL containing the original PNG bytes. Explicitly record image
  detail. Do not put the base64 image into the text JSON as well. Preserve camera
  calibration, observation ID/time, robot state, remaining budgets and bounded
  public action history; do not add tools, files, private truth, evaluator results,
  filesystem paths, previous_response_id or provider-managed conversation state.
- [ ] Use the existing action schema under strict `text.format` JSON-schema output;
  keep the existing prompt, primitives, guards and simulator budgets unchanged.
  Revalidate the public boundary rather than serializing arbitrary added fields.
  Validate configuration and malformed PNG/base64 before invoking transport.
- [ ] Validate the provider envelope before accepting an action. An incomplete,
  failed or malformed envelope must never execute an apparently valid command
  nested inside it. Detect refusal, missing output, malformed content, multiple
  action messages, invalid JSON/commands and unexpected tool output. Reasoning
  metadata may be ignored, never interpreted as a command. Reuse the runner's
  primitive validator. No retries, repaired JSON, replacement commands or fallback.
- [ ] Retain separate adapter attempt records with the exact request and raw mocked
  response, provider status/ID/model/usage when available, image/body hashes, wall
  latency and classified failures. Mark them as injected/offline evidence. Keep
  callback invocation counts honest and do not overwrite existing records. Preserve
  raw failure evidence and pass only a command/refusal outcome to the visual loop.
  Keep private evaluation separate. Do not claim estimated dollar costs or invoice
  amounts from fixtures; retain usage as reported and label missing usage unknown.
- [ ] Provide a dry request-export command/example that uses an existing saved public
  observation or payload, writes to a new path, and cannot send a request. Require
  explicit model configuration; no existing evidence overwrites. Retain one compact
  request manifest (hashes, field layout, fixture source, image size), avoiding
  another large duplicate PNG/base64 artifact in Git when source is already saved.
- [ ] Write `experiments/humanoid-pick-place/protocols/V1_PROPOSAL.md` as an unfrozen,
  unexecuted first visual LLM development pilot draft. Propose a single seed-820
  initial pilot, fixed camera and public input condition, paused inference, existing
  20-call/25-second hard limits, fixed prompt/schema/model configuration, stop rules,
  private scoring and full failure denominators. Reuse L2's model as the proposed
  comparator condition rather than silently changing it. Identify remaining live
  transport, verified multimodal spend reservation, explicit total spend approval,
  API access verification and frozen source hashes as prerequisites. Do not present
  a mock as LLM performance or this pilot as a matched formal benchmark. Do not
  fabricate an executable live CLI or mark proposal prerequisites complete.

Keep the implementation focused: a request builder, envelope adapter and injected
transport are sufficient. Actual HTTP/credential access and spend enforcement are
a later bounded task. In particular, do not copy the text-only L2 client's 120 kB
prompt cap or assume base64 bytes equal billed image tokens.

## Official documentation

Codex consulted these official pages on 2026-09-13. Verify specific API fields here
if needed; no provider account access is needed for documentation.

- Responses image inputs use `input_text` and `input_image`, including PNG data URLs:
  [Images and vision](https://developers.openai.com/api/docs/guides/images-vision).
- Responses structured output uses `text.format` with strict JSON schema; handle
  refusal and incomplete output explicitly:
  [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
- Record the response envelope and usage without inferring success from output text:
  [Create response](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

## Verification and handoff

- [ ] Production request-builder test: decode actual image item and compare its hash
  to source; assert exactly one image, no image duplication in text, stable schema,
  explicit configuration, bounded history and planted private fields excluded.
- [ ] Production adapter tests through injected transport: success, refusal,
  incomplete/failed status even with valid embedded action, malformed/ambiguous
  output, transport exception, unknown usage, no retry, no overwrite and retained logs.
- [ ] At least one end-to-end `run_visual_episode` test exercises the real adapter
  and fake transport, asserting exact captured ID/guarded action, truthful counts
  and failure termination before execution. Preserve Task 004 budget/report tests.
- [ ] Verify import, constructor without transport, request export and test runs do
  not access credentials or network. Test the actual boundary, not just a flag.
- [ ] Run focused tests and full unittest discovery after final code; retain exact
  commands and logs. No repeated optimization or fresh evaluation.
- [ ] Update runner documentation, PLAN and `coordination/agy/reports/005-completion.md`.
  Distinguish adapter readiness from live-run readiness. Run working and revision
  `git diff --check`, commit and push only the task branch, return exact local/remote
  tip hashes and stop ready for Codex review.
