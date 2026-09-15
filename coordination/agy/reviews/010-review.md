# Task 010 — interrupted draft review

Status: revisions required. Base `9445fbef35e2944165314d306b4b214ef7d4bd9c`.
AGY conversation `92e23a3a-9261-4f25-a71e-36dcb7e584e3` was stopped by Codex
at 2026-09-15 02:48:33 UTC before commit/handoff. The working changes are retained.
Tracked draft diff SHA-256: `a982c4b1e6117d5ecba0c14710a17321bfeb6d1abf6b60aeecff4319b19ea517` (untracked schema reviewed separately).

## R1 — high: default runner fails and loses its report

`effective_cond` is assigned only inside the execution_metadata branch, then used
in parsing and finalization unconditionally. With default execution_metadata=None,
a normal one-call hold raises UnboundLocalError and report.json is absent.
Initialize the default before branching. Test normal default operation and default
failure/interruption report retention with fake capture/interface and no physics.

## R2 — high: historical C2 audit regression

Existing test_saved_c2_failure_reproduces_with_physics_and_model_disabled now fails
with `Execution source changed: humanoid_sim/codex_policy.py`; the source-mismatch
test also fails before reaching its intended environment mutation. The audit compares
all historical controller files against current HEAD, including files it never executes.
You are authorized to make a minimal compatibility correction to audit_codex_c2.py
and its tests: keep the pinned archive hash, full member verification, and historical
execution provenance intact; distinguish those from current audit runtime dependencies.
Explicitly verify every actual local audit dependency (including transitive dependencies
and scene/model assets) used to reconstruct/evaluate saved states. Continue to reject
mismatched environment/scene inputs before output. Do not blanket-disable source checks,
skip tests, rewrite frozen archives, or regenerate committed historical C1/C2 audit
artifacts. Document the provenance distinction. Test unrelated controller edits allowed
and actual audit dependency changes rejected. Preserve archive/member corruption tests.

## R3 — high: assessment accounting drops failures and string responses

Independent fake-interface reproduction: valid first C3 response followed by
MalformedResponseError gives model_calls=2, completed_actions=1, but visual_assessments
contains only call 1 because it copies the policy's successful-assessments list.
A valid JSON-string response completes its action yet its assessment row is null.
Build the report from every attempted call with explicit status and missing/malformed
assessment state, including failures after earlier valid responses. Parse the current
response to retain its assessment, never borrow a stale last_assessment. Preserve raw
CLI output for adapter-side failures and link decision artifacts/provenance. Keep full
prompt/static/schema/image/source/config identity where available, even for failed calls.
Test valid then malformed/timeout/interruption, string input, and no history leakage.
Only the command reaches the interface, with no retries or assessment-based correction.
Reviewer reproduction is /private/tmp/agy-010-review/runner-check.py.

## R4 — high: offline boundary violated by the test selection

The task explicitly requires injected doubles with no reset or physics stepping.
Initial batch logs show whole test_codex_policy and test_humanoid_visual_policy_runner
modules executed; they instantiate Environment/reset and execute mock commands in
MuJoCo. New C3 tests also use Environment.reset. These are synthetic tests, not model
trials, but cannot be described as zero physics/reset. Acknowledge this in completion.
Before ANY further tests, replace new/affected C3 runner fixtures with archived public
observations and fake sessions/interfaces. Use a checked-in offline test entry point
that patches Environment construction/reset and mujoco.mj_step/mj_step1/mj_step2 to
raise, and selects only applicable offline tests (or convert the affected legacy tests
to equivalent doubles without weakening assertions). Also forbid actual Codex process
launch/model calls; mock subprocess fixtures remain allowed. Do not run a full discovery
or existing physics tests. Retain a fresh successful guarded test log. This is a software
check, not a fresh episode, and must be labelled accordingly.

## Required completion

Finish all Task010 docs/preflight/artifact/hash requirements after these corrections.
The independent golden check already passed all 12 C1/C2 archived prompts/images and
the exact C3 instruction/schema. Preserve those: expected C3 static SHA-256
`de0525e07f9470be60f9e01c4d720ad4f65260fd54b08065708e4096ce6313d0`.
No C3 freeze, live model call, API, new physics, source capture mutation or held-out
seed use. Commit/push only agy/010-c3-offline-preparation and return exact tip.
