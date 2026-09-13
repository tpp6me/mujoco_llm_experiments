# AGY task 006 — Live transport, spending controls and pilot readiness

Status: **cancelled by user before implementation**. Historical proposed branch: `agy/006-visual-live-transport`.
Use `/private/tmp/mujoco-llms-agy-006`, starting from the main commit containing
this brief. Record the exact starting commit. Prerequisite: Task 005 accepted at
integration `f92c741eec97905e2bd52ebff533438581a2d06b` (203 passing tests).

Read `coordination/agy/WORKFLOW.md`, `coordination/agy/reviews/005-acceptance.md`,
`experiments/humanoid-pick-place/PLAN.md`, `VISUAL_POLICY_RUNNER.md`,
`protocols/V1_PROPOSAL.md`, `humanoid_sim/visual_provider_adapter.py`,
`visual_policy_runner.py`, `llm_runner.py`, and relevant tests.

## Cancellation — 2026-09-13

The user instructed Codex to work directly and not use OpenAI APIs. This brief is
retained as a historical proposal and must not be executed. No AGY Task 006 process
or worktree was created. See [current execution direction](../../EXECUTION_POLICY.md).

## Historical objective and boundaries

Implement the remaining software needed for one future visual LLM pilot: an
explicitly enabled HTTPS transport, persistent conservative spend reservations,
and a pilot entrypoint/preflight artifact. Exercise the full path with fake HTTP
responses. This task implements live capability but does not execute it against a
provider. A later reviewed Task 007 can freeze and run the proposed seed-820 pilot
once the user approves its concrete budget and configuration.

- [ ] Edit/test/commit/push only the dedicated task branch. No main integration,
  history rewrite, dependency changes, hardware or new providers/models.
- [ ] No actual API-key lookup, provider/account/model-list/token-count request or
  paid invocation during AGY execution. Code may implement lazy credential lookup;
  tests must inject a fake credential provider and fake network boundary.
- [ ] Public documentation reads and git push are allowed network operations.
  Do not confuse these with authorization to contact a model endpoint.
- [ ] Reuse the primary `.venv/bin/python`, existing dependencies and public saved
  seed-820 inputs. Existing mocked/seed-820 unit regressions may run; do not generate
  fresh rendered episodes, rerun optimizers or touch held-out seeds 840–849.
- [ ] Preserve scene/physics/camera, guarded primitives, prompts, L2 behavior,
  existing artifacts and temporal estimators. P5 remains unqualified at 5.8715 mm
  versus the unchanged 5.0 mm mean gate. Keep V1 unfrozen and unexecuted.

## 1. Explicit HTTPS transport

- [ ] Add a focused transport module using the Python standard library. Target only
  `https://api.openai.com/v1/responses`; no configurable third-party endpoint,
  redirects, automatic retries, polling, streaming or tool execution. Preserve TLS
  certificate verification. Use an explicit finite timeout and bounded response
  read. Keep socket/open/request and credential dependencies injectable.
- [ ] Import, construction and dry preflight must not read credentials or create a
  connection. Retrieve a key only after explicit live opt-in, configuration validation
  and successful persistent budget reservation. Missing key stops before HTTP.
  Never log Authorization headers, key values or arbitrary exception strings that
  could contain a key. Use structured sanitized HTTP/error metadata and request IDs.
- [ ] Return one envelope plus optional request-ID string to the accepted adapter.
  Retain HTTP status, request/response IDs, body hash, usage and classified failures
  in a separate transport/ledger record. Bound malformed/oversized responses.
  Transport timeouts, HTTP 4xx/5xx, malformed bodies and interruptions get one attempt,
  no retry, and no replacement action. Preserve private score isolation.
- [ ] Require the proposed model `gpt-5.6-sol`, reasoning `low`, at most 2048 output
  tokens, one 960x720 PNG at high detail, canonical public prompt/schema, and standard
  service tier for the first pilot. Reject unsupported configurations rather than
  silently applying these prices to another model/detail/tier. If adding service-tier
  configuration to the adapter, ensure its recorded request hash matches the exact
  wire body; do not mutate it after hashing/reserving. Preserve Task 005 default dry
  request hashes and historical exports.

## 2. Conservative persistent spend reservations

- [ ] Implement one auditable run ledger with an explicit positive finite total
  budget (no default authorized spend). Record configuration, pricing source/date,
  request hashes, invocation/transport counts and a reservation before each possible
  network call. At most 20 attempts and the existing 25-second simulated deadline
  still apply independently of money. Require a new run directory; prevent a second
  process from concurrently using the same ledger, or implement atomic reservation
  locking. No distributed or general account billing system is needed.
- [ ] Establish a conservative request-cost estimate from enforced input bounds:
  count ALL non-image UTF-8 request bytes (instruction, public text/history, strict
  schema and other JSON framing), declared wrapper overhead, image-token bound and
  max output tokens. Do not charge base64 bytes as text tokens or assume history is
  a fixed 1,500 tokens. A suitable narrow design is a 65,536-byte non-image cap,
  4,096-token framing allowance, and the documented image estimate with a rounding
  margin. Document the byte-to-token assumption as a local conservative estimate,
  not an invoice guarantee; reject unsupported content instead of extrapolating.
- [ ] Account conservatively for input/cache-write pricing as well as output. Current
  cited model guidance lists standard input $4/M, cached input $0.40/M, output $20/M
  and cache writes at 1.25 times input price. A reservation can use the highest
  applicable input rate for all input tokens without relying on cache savings.
  Keep numeric rounding conservative (integer monetary units or Decimal preferred).
  Validate caps and arithmetic; booleans/NaN/negative values are not valid budgets.
- [ ] Prefer the simple conservative policy: reservations remain charged to the local
  allowance for the whole run, even when reported usage is lower. Record usage-based
  estimates separately, never as invoices. Missing/malformed usage, mismatched
  returned model/tier, timeout, malformed response, refusal or unknown dispatch must
  never release an uncertain reservation. A process restart must preserve pending
  liability; fail closed on malformed or inconsistent ledger state. Do not add
  automatic episode resumption/retry after an uncertain interruption.
- [ ] If provider-reported usage exceeds the reserved assumption, retain the actual
  overage and stop further calls; do not clamp the evidence to make the budget pass.
  The estimate is a local spending guard, not control of provider invoices or other
  account users. Record this limitation without weakening pre-dispatch checks.
- [ ] A budget rejection or failed ledger write must occur before credential lookup,
  socket creation or robot execution. Keep adapter call counts distinct from actual
  HTTP dispatches. Pending dispatch is unknown, not proven false; preserve the Task
  005 interruption fix. Never silently suppress audit write failures.

## 3. Pilot command and reviewable preflight

- [ ] Provide a separate pilot entrypoint that defaults to dry/preflight behavior.
  Dry mode uses an archived public payload, produces configuration, request/body/image
  hashes, cap calculations and a complete 20-call reservation projection, and requires
  no credentials, model endpoint, simulator reset or rendering. Explicitly label
  proposed budget values as unapproved; no paid cost has been measured.
- [ ] Implement the live execution path behind explicit `--execute-live` (or similarly
  clear opt-in), model and budget options. Restrict its real episode to seed 820 and
  fixed camera. Validate scope, directories, hard limits, configuration and source
  hashes before simulator reset or rendering. Wire the existing runner, adapter,
  budgeted transport and VisualSession; do not create a second action loop or use
  private evaluator success as an early stop.
- [ ] Make provenance mode truthful across runner, adapter and transport: mocks/dry
  are offline; a future real HTTP invocation cannot inherit hard-coded
  `offline_only: true`. Record exact configuration and source/prompt/schema hashes,
  pricing assumptions, request identities, ledger path and private evaluator output.
  Model inputs must not include ledger balances in place of simulator budgets,
  credentials, filesystem paths or evaluator truth.
- [ ] Update V1_PROPOSAL and create `VISUAL_LIVE_TRANSPORT.md` plus a compact retained
  preflight JSON. Include the actual implemented commands, a concrete proposed total
  budget derived from enforced caps, cost limitations, and remaining user approval /
  source-freeze / account-access checks. Do not invent a completed live qualification
  or mark proposal prerequisites accepted before review. The next handoff should let
  Codex review the exact code, command, configuration and proposed amount before
  asking for paid execution approval. AGY must not invoke the live command.

## 4. Production-path verification

- [ ] Tests with fake HTTP/credential dependencies verify exact endpoint, TLS/redirect
  policy, POST body/hash, bearer-header placement, timeout, request IDs and error
  handling without sending any request or reading a real key. Check secrets never
  enter retained records, even in exception text.
- [ ] Reserve-before-dispatch and no-dispatch-on-low-budget/log-write failure tests;
  boundary budgets, invalid options, maximum history/request size, image-token math,
  unknown usage, mismatched model/tier, usage overage, refused/incomplete responses,
  timeout, interruption and reopened ledger accounting. Test actual file state and
  callback counts, not just helper return values. No reservation recycling on failure.
- [ ] End-to-end runner -> adapter -> budgeted transport -> fake HTTP tests exercise
  one valid guarded action and no action after a transport/budget failure. Preserve
  single-use observation IDs, hard simulator limits and unknown-movement accounting.
- [ ] Test dry CLI and invalid live configuration reject before credentials/network/
  simulator setup; verify existing Task 004/005 offline paths stay offline by default.
- [ ] Run focused tests then full unittest discovery once final code is ready; retain
  exact commands and logs. The baseline is 203 tests. Do not repeat expensive suites
  without changes or a specific failure to resolve.
- [ ] Run working and base-to-tip `git diff --check`, update PLAN/runner docs and
  `coordination/agy/reports/006-completion.md`, commit/push only the task branch.
  Return exact local/remote hashes, tests, proposed pilot amount, known limits and
  report path; stop ready for Codex review. Do not launch Task 007 yourself.

## Official sources checked by Codex, 2026-09-13

- [API authentication and request IDs](https://developers.openai.com/api/reference/overview).
- [Responses parameters](https://developers.openai.com/api/reference/cli/resources/responses/methods/create):
  max_output_tokens includes reasoning and visible output; pin the intended service
  tier and retain the actual returned tier.
- [GPT-5.6 Sol pricing](https://developers.openai.com/api/docs/models/gpt-5.6-sol):
  verify current rates, cache writes and long-context conditions before freezing.
- [Images and vision](https://developers.openai.com/api/docs/guides/images-vision):
  high detail for this model uses 32-pixel patches, a 2,500-patch/2,048-pixel sizing
  budget and a 1.2 multiplier. Unresized 960x720 gives ceil(30*23*1.2)=828 estimated
  image tokens; allow for documented rounding uncertainty. This is not the total
  request cost. Keep production scope narrow rather than adding other detail modes.
