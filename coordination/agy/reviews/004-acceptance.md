# Codex acceptance — task 004

Date: 2026-09-13.
Reviewed AGY tip: `64c8907a39f8285c7e8fa2245a53454d1cc75474`.
Branch: `agy/004-visual-policy-scaffold`.
Decision: **accepted with integration fixes**, limited to the offline scaffold.

## Outcome

The public RGB/proprioception loop, injected offline callable, guarded fresh-ID
execution, hard 20-call/25-second budgets and explicit failure logging are accepted.
This is implementation evidence, not an LLM trial or placement result. Historical
four-action seed-820 stub artifacts are unchanged and retain their original source
provenance; later runtime budget fields were not retroactively inserted.

## Review findings and integration corrections

AGY addressed R1's non-finite output, malformed envelope, observation and execution
exception handling and R2's caps, configuration validation, duration rounding,
runner/adapter consistency, CLI scope and actual-budget provenance. Independent
full discovery on the exact AGY tip passed **173 tests in 144.462 s**.
[Exact-tip test log](004-r2-tests.txt).

A remaining R1 case was reproduced before integration: a result declaring
`status: completed` with `end_time_s: null` or a string raised after incrementing
completion; NaN, boolean or regressing times could continue to the action limit.
Codex added regressions that failed on that tip, then corrected the integration:

- Validate result status and finite, non-boolean, nonregressing execution times
  before counting completion. Preserve VisualSession's timestamp-free stale-ID
  rejection as a rejection.
- Stop on malformed results and retain the attempt. Record
  `execution_outcomes_unknown` for malformed execution results or exceptions;
  report final time as null if no trustworthy post-execution state is available.
  A failed attempt must not imply zero physical movement.
- Retain unexpected loop exceptions explicitly, surface archive errors separately,
  and validate adapter budget values with the same hard-limit validator.
- Clarify historical smoke provenance and use a new-directory CLI example.

The added episode tests cover null/string/NaN/boolean/regressing result timestamps,
unknown movement after an execution exception and a simultaneous archive error.

## Independent validation

From the integrated primary checkout:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

**175 tests passed in 146.094 s**. [Integration log](004-integration-tests.txt).
The focused visual runner suite passed 30 tests before the final full discovery.
Working-tree whitespace checks passed. Review introduced no provider API call,
credential lookup, rendering demo, fresh held-out inputs, physics change or temporal
optimizer run. Existing task evidence remains unchanged.

## Next step

[Task 005](../tasks/005-visual-provider-adapter.md) prepares the Responses image
adapter using injected transport and a concrete unfrozen pilot draft. Paid execution,
live transport and spend approval remain later work. P5 development mean remains
5.8715 mm against the unchanged 5.0 mm gate; seeds 840–849 remain untouched.
