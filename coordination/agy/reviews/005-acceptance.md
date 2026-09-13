# Codex acceptance — task 005

Date: 2026-09-13.
Reviewed local/remote AGY tip: `12da6162a4d9046d36d79ee8eaea2de304a68a18`.
Branch: `agy/005-visual-provider-adapter`.
Decision: **accepted with integration fixes**, limited to the offline adapter.

## Outcome

The adapter constructs an image-capable Responses request from the public payload,
requires explicit model and injected transport, validates the provider envelope,
retains separate attempt evidence, and supports dry request export. The V1 pilot
proposal remains unfrozen and unexecuted. There is no HTTP transport, credential
access or paid pilot in this task, and no claim of model manipulation performance.

## Review disposition

AGY resolved the prior R1–R3 reproductions: preparation failures retain records
with zero callbacks, pending request bytes precede transport, empty tuple responses
are classified, truncated raster data is rejected, export aliases are blocked,
model selection is explicit, and the pilot's causal/token/stop-rule claims are
corrected. Independent full discovery on that exact tip passes **201 tests in
177.560 s**. [Exact-tip log](005-r2-tests.txt).

Two residual cases were reproduced and corrected locally during integration:

- A list or tuple containing two complete envelopes silently selected the first.
  The transport contract now accepts one dictionary/JSON envelope, optionally paired
  with a string/null request ID in an exact two-element tuple. Response lists,
  malformed metadata and extra tuple members are rejected and retained.
- An injected KeyboardInterrupt after dispatch left `transport_invoked: false` in
  the pending record. Pending records now use null for uncertain dispatch. Caught
  KeyboardInterrupt/SystemExit record interruption in adapter and final episode
  reports, then propagate without retry. Known callbacks retain true; preparation
  failures retain false. An unfinished record does not imply zero spend.

Also stopped suppressing preparation-log write failures and strengthened the offline
boundary test to raise on API-key lookup, without reading/replacing an actual key.
The new regressions failed on the AGY tip before these corrections. The valid
(envelope, request ID) path and existing Task 004 budget/error guards still pass.

## Independent integration validation

```sh
.venv/bin/python -m unittest tests.test_visual_provider_adapter \
  tests.test_humanoid_visual_policy_runner -v
.venv/bin/python -m unittest discover -s tests -v
```

- Focused: **58 tests passed in 9.384 s**.
- Full discovery: **203 tests passed in 176.403 s**.
  [Integration log](005-integration-tests.txt).
- Working/revision whitespace checks passed.
- Dry export to a new temporary directory reproduced both the retained request
  SHA-256 and image SHA-256 exactly. Existing request manifest and all historical
  experiment artifacts remain unchanged.
- No provider/account request, credential lookup, rendering demo, optimizer rerun,
  fresh held-out episode, scene/physics change or hardware operation was performed.

## Remaining work

Live HTTPS transport, conservative multimodal spend reservation, explicit pilot
spend approval, account/model access verification and frozen V1 source hashes
remain prerequisites. See [V1 proposal](../../../experiments/humanoid-pick-place/protocols/V1_PROPOSAL.md).
The passive P5 mean remains 5.8715 mm against the unchanged 5.0 mm gate, and seeds
840–849 remain untouched. AGY Task 005 is complete; no AGY task remains running
at this acceptance checkpoint.
