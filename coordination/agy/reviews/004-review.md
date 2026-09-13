# Codex review — task 004

Date: 2026-09-13.
Reviewed exact tip: `89006428b1a3762993cb882fbf2acc2ef533afa8`.
Branch: `agy/004-visual-policy-scaffold`.
Base: `9c143d45625e0780206fd64a7771daf0633e7671`.
Decision: **changes requested**. No merge or live provider experiment.

## Summary

The provider-neutral runner, explicit public payload construction, guarded fresh-ID
execution, stub CLI and four-action seed-820 smoke evidence are present. The smoke
is correctly labeled offline and does not claim successful placement or LLM skill.
The implementation still needs reliable whole-episode failure accounting and
consistent hard budget enforcement before accepting the scaffold.

## R1 — High: malformed inputs or execution failures can lose the final report

Locations: `humanoid_sim/visual_policy_runner.py:580-705` and response parsing.
The loop catches errors from the model callable and selected parser exceptions,
but observation preparation, several parser structure errors, execution and history
sanitization are outside effective failure handling. Logging a rejected non-finite
response also raises because `raw_response` still contains NaN while `write_json`
uses `allow_nan=False`.

Independent reproductions with injected sessions and temporary log directories:

```text
NaN response raised ValueError; final report exists: False
Malformed response envelope {'output': None} raised TypeError; final report exists: False
Execution exception raised RuntimeError; final report exists: False
```

These are recoverable input/interface failures for which the task requires explicit
termination without retry. A pending call file alone does not describe the observed
exception or whether an execution attempt took place. Invalid observations (missing
keys/corrupt image metadata) can fail similarly before a call is recorded.

Required: cover the entire iteration lifecycle, including observation preparation,
response parsing, guarded execution and outcome/history validation. Stop without
retry or fallback and retain a final report plus the failed attempt when one exists.
Keep stage-specific error reasons and correct capture/model-call/action-attempt/
completion counts; do not claim no movement if an execution exception could have
occurred after partial movement. Preserve invalid raw model output using an explicit
JSON-safe diagnostic representation when needed, without silently dropping the
invalid value or creating NaN JSON. Do not suppress evaluator/archive errors as if
all artifacts were saved successfully. Genuine filesystem failure may limit what
can be written; report that limitation rather than falsely asserting completion.

Also reject booleans in numeric command fields: `seconds: true` currently becomes
`1.0`, although the action schema declares a number. Normalize malformed provider-
style envelopes to a controlled malformed-response result. Do not expand provider
integration; the callable remains offline and provider-neutral.

Add regressions through `run_visual_episode`, not just the parser: NaN/Infinity
inside dictionary responses, malformed envelope types, unserializable callback
output, malformed observation, execution exception, malformed action result and
boolean numeric commands. Assert retained termination/attempt records and no extra
model or action call. Preserve the existing valid, refusal and collision cases.

## R2 — High: enforce hard caps and one effective deadline before execution

Locations: `VisualPolicySession.__init__/execute`, `run_visual_episode`, CLI
argument handling and `provenance`.
The CLI and constructors accept arbitrary `max_calls` and `deadline`, including
values above the promised 20 calls / 25 simulated seconds. The loop and adapter can
also have different limits; the loop checks time only before the model call and
after the action, while the adapter uses its own deadline.

Independent reproduction using the real `VisualSession`/guarded interface with a
mock renderer and existing development seed 820:

```text
max_calls=21 in runner/adapter: 21 completed hold calls, simulated t=0.920 s
runner deadline=0.55, adapter deadline=25, hold=0.1 at t=0.5: executes to t=0.600 s
```

The latter overshoots the configured episode deadline. The narrow injected-session
path exhibits the same issue because the loop never validates the proposed duration
against its captured observation time before calling execute. Adapter fallback to
`now=0` when no environment exists is not a trustworthy budget check.

Required: validate finite positive configuration, reject booleans/non-integer call
limits and values above the hard 20/25 caps, and allow smaller smoke-test budgets.
Enforce one effective budget across runner/adapter or explicitly reject inconsistent
configuration. Check the rounded-up action duration against the current captured
simulation timestamp before invoking execution; keep the existing freshness and
collision checks authoritative. Validate CLI configuration before simulator reset
or rendering. Honor Task 004's seed-820-only optional real smoke scope at its
execution entrypoint. Do not enable new seeds/camera experiments as part of this fix.

Record actual configured call/deadline limits in run provenance in addition to
protocol hard caps. The current four-call demo provenance reports only max_actions
20, so it does not identify the runtime cutoff that terminated that smoke run.
Add end-to-end regressions for caps above 20/25, NaN/invalid options, reduced budgets,
runner/adapter disagreement, rounding at the deadline and no execution past limits.
Use mocks or seed 820 only; no fresh held-out inputs, APIs or optimizer runs.

## Independent checks

- Verified task tip and origin ref at `8900642`, clean task worktree and clean main.
- Full discovery from the task worktree with
  `/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v`:
  **161 tests passed in 170.616 s**. [Retained log](004-tests.txt).
- `git diff --check 9c143d4..8900642` passed.
- Read the runner, tests, public-boundary implementation and retained smoke report.
- Reproduced failure-report loss and boolean acceptance using injected sessions;
  [script](004-repro.py), run from the task worktree with `PYTHONPATH=.` and the
  shared interpreter. Also independently reproduced cap/deadline failures with the
  real guarded interface and mock renderer on existing seed 820.
- No graphics regeneration, fresh held-out data, provider API or hardware use during
  review. Existing exact-state runner, physics and temporal estimators are unchanged.

## Direct revision instructions for AGY

Resume the same branch/worktree and add commits addressing R1/R2. Preserve resolved
payload isolation and offline-only behavior. Run the new episode-level failure and
budget tests, full discovery and diff checks. Update documentation, provenance and
`004-completion.md` with finding-by-finding evidence. Preserve the original smoke
artifacts as historical if behavior changes; a new small seed-820-only stub demo
may be retained separately if needed. Do not rerun P5 optimization or call a real
model. Commit and push only the task branch and return exact local/remote tip hashes;
stop ready for review without main integration.
