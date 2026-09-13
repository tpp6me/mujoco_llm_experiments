# Codex review — task 005

Date: 2026-09-13.
Exact reviewed local and remote tip: `ea09ce7dc4a7fd1e091465fbb0912c26ff7ac613`.
Branch: `agy/005-visual-provider-adapter`.
Base: `bcdeadb0d02bdef9dd975742b23650c64a6de56b`.
Decision: **changes requested**. No merge, paid request or fresh experiment.

The adapter emits one actual image item and a separate public text payload,
rejects ordinary incomplete/refused/ambiguous responses, and integrates the runner's
exception classifications. Full discovery independently passes **194 tests in
145.240 s** ([log](005-tests.txt)); revision whitespace checks pass. These tests
miss the following reproduced cases. The task worktree is clean and the pushed
branch matches the reviewed hash. AGY's batch process exited successfully.

## R1 — High: retain attempts across the complete adapter lifecycle

`VisualProviderAdapter.__call__` increments `call_count` before request validation,
but creates no record until transport returns or selected exceptions are handled.
The pending record is never written before transport. Metadata extraction is outside
the envelope exception guard and indexes an empty tuple unconditionally.

Independent reproductions using the saved public request and injected transport:

```text
pending record exists during transport: False
empty tuple: IndexError record exists: False
bad PNG: ValueError call_count: 1 actual callbacks: 0 records: []
```

A malformed callback result or interruption can therefore leave no adapter request
or raw failure evidence; a preflight error is also counted as a call even though
transport was not invoked. This violates the declared retained audit trail and
honest callback accounting, independently of future paid execution.

Required: separate adapter invocation/preparation attempts from actual transport
calls, and make both counts unambiguous. Retain preparation failures without
pretending a callback occurred. Persist a pending request record before invoking
transport when recording is enabled. Enclose metadata extraction and envelope
validation in the same failure-accounting boundary. Empty/invalid tuples and other
malformed results must retain raw evidence with a controlled malformed result;
never retry. If an initial record cannot be written, do not invoke transport.
Retain refusal, unknown usage and interruption semantics without claiming zero cost.
Keep explicit transport injection and offline labels. Do not implement live billing.

Add production-path tests checking that pending bytes exist inside the callback,
malformed tuple/list/scalar results retain evidence, preflight errors have zero
transport calls, and a pre-transport filesystem error prevents the callback.
Preserve the runner's accurate refusal/malformed/exception classifications.

## R2 — Medium: validate complete images and distinct export destinations

`validate_png_base64` only opens the PNG header without decoding/verifying the
complete image. The first 100 bytes of the existing 98,944-byte PNG, with its hash
updated to match the truncated bytes, pass `build_responses_request`.

`export_request(source, output, manifest_path=output)` also succeeds: it writes
the request and then overwrites it with the manifest. Reproduced final file has no
`input` field. The initial exists checks cannot detect two aliases of a new path.

Required: verify/decode the full PNG before transport; reject truncated/corrupt pixel
data even with a correct hash of those bad bytes. Reject equal/resolved-alias output
and manifest paths before either write; preserve source and existing artifacts.
Test both through production entrypoints. No resizing, camera or physics changes.

The brief also requires explicit model configuration. Public builder, adapter and
export functions currently default to a paid model despite docstrings requiring
explicit selection. Require model explicitly at these boundaries (the proposal can
still name the existing L2 model), validate the declared configuration before
transport, and update tests/examples to pass an intentional model. Do not add API
calls to establish availability. Use fresh example output/manifest paths; the
completion-report command currently targets a committed manifest and thus fails.

## R3 — Medium: keep the pilot draft consistent with the experiment

Correct `V1_PROPOSAL.md` and matching completion/doc claims:

- Remove private evaluator task success from loop stop rules. The accepted runner
  stops on public control/error/budget conditions and scores post-hoc; it does not
  consult private success during the loop. Introducing an oracle stopping condition
  changes the scientific condition and is outside Task 005.
- Reusing a model/configuration does not establish that observed performance
  differences are caused by the visual condition. Existing L2 trials and a single
  seed-820 pilot are not matched randomized trials; retain the continuity claim but
  remove the causal attribution claim.
- Remove the unsupported 853-image-token/four-tile calculation and the unmeasured
  approximately 1,500-text-token assumption. Official current guidance for
  `gpt-5.6-sol` uses 32-pixel patches and a 1.2 multiplier, with high detail limited
  to 2,500 patches and a 2,048-pixel dimension limit. For this unresized 960x720 image,
  the documented formula gives ceil(30*23*1.2) = 828 estimated image tokens, not a
  complete request reservation or an invoice guarantee. Text/history/schema/output
  costs and uncertainties must still be bounded in the later spend task. It is
  sufficient here to leave the reservation unimplemented and link official guidance.
  [Official image sizing and tokenization, checked 2026-09-13](https://developers.openai.com/api/docs/guides/images-vision).
- Do not promise a zero-cost account preflight without specifying a verified method.
  Keep model/account access verification a future prerequisite and make no calls.
- Clarify the completion report's implementation commit
  `a4cae354778227ee48a1263cb984f0bf71120316`: it exists locally but was amended and
  is not an ancestor of the pushed tip. Name the pushed reviewed tip as well and
  distinguish historical implementation snapshots from later revision tips. Keep the checklist's review
  acceptance unchecked until Codex accepts a specific tip.

## Reproduction and revision instructions

From the task worktree:

```sh
PYTHONPATH=. /Users/praveen/work/github/mujoco-llms/.venv/bin/python \
  /Users/praveen/work/github/mujoco-llms/coordination/agy/reviews/005-repro.py
```

[Reproduction script](005-repro.py) uses saved public seed-820 input, injected
callbacks and temporary output only. No credentials, paid provider calls, physics
changes, rendering, held-out inputs or optimizer runs were used in this review.

Add commits to the same branch addressing R1–R3. Preserve Task 004 integration fixes,
existing historical artifacts and P5 gates. Keep the adapter offline with injected
transport. Run meaningful new regressions, focused tests and full discovery once
final code is ready; retain logs and correct the completion report. Commit/push only
the task branch and return exact local/remote hashes. Stop ready for Codex review.
