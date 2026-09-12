# Paused-time exact-state LLM runner

The runner connects GPT-5.6 Sol to the same version-2 move/hand/hold interface used
by the qualified G2 conventional policy. This is exact-state action control:
no images, visual perception, free-standing balance, or walking are supplied.

## Run

Configure `OPENAI_API_KEY` in the process environment, then use a fresh directory:

```sh
.venv/bin/python -m humanoid_sim.llm_runner --output runtime/humanoid/new-llm-pilot --seeds 700 701 702 --budget-usd 4.5
```

The named seeds are development cases after their first use. Select and freeze new
seeds for a future confirmatory comparison. Existing output directories are never
overwritten; there is no implicit resume or retry. Run one process at a time.
The CLI currently selects `gpt-5.6-sol` with low reasoning and a 2048-output-token
limit. Changing these constants requires a new frozen protocol and source snapshot.

## Decision boundary

Each seed runs the conventional G2 policy and a separate LLM episode from the same
randomized reset. Both use the same interface, 25-second simulated deadline,
20-action maximum, primitive bounds and terminal rejection policy. Physics pauses
between calls. The model receives the static robot/task contract, current public
exact-state observation, its own prior actions and execution responses, and
remaining time/actions. Conventional actions and outcomes, scorer fields, private
source/runtime files, and the tuned pickup recipe are not included in its inputs.

The Responses API receives text plus a strict response schema and no external
tools. It cannot inspect local files or run code. The runner adds only the schema
version, fixed instruction version and unique request ID to each model command;
it does not change pose, orientation, closure or duration. All such choices,
including waiting to settle, belong to the acting policy. An over-deadline,
unreachable, malformed or colliding action is rejected without correction and
ends the episode. There is no private-success-based early stopping.

The conventional policy uses its qualified recipe. Its final task outcome, like
the LLM's, is measured independently from physics. A successful placement and a
strict contact-quality pass remain separate outcomes. Three development cases do
not satisfy the 100-trial qualification gate or establish comparative superiority.

## API handling and artifacts

The implementation uses the standard-library HTTPS client, with one request per
action and no automatic retries. It requests `store=false`. Each call has a
45-second socket timeout; this is not a separate hard whole-episode wall deadline.
The runner handles refusals, incomplete or malformed responses, HTTP errors and
transport failures as episode-ending outcomes. Failed and interrupted calls stay
in the logs; HTTP error bodies are not generally echoed to avoid credential leaks.
The L1 schema-error diagnostic is recorded separately with credential redaction.

Each episode retains:

- `call_NNN.json`: exact request, returned raw response when available, provider
  request/response IDs, requested/returned model, usage, service tier, round-trip
  duration and cost estimate/reservation. A pending reservation is written before
  dispatch. Authorization headers and API credentials are excluded.
- `episode.npz`, `metadata.json`, `events.json`: physics state, frames, all action
  attempts, responses and private scorer data. State is saved after every action.
- `report.json`: independent outcome, termination/error, action/model-call counts,
  unknown-usage count, estimated cost and source/configuration hashes.

The run root holds `manifest.json` and an incrementally saved `summary.json`.
Local runtime artifacts are ignored by Git. Versioned reports, attempt archives,
source snapshots and test logs are stored under this experiment's `results/`.
The archived source and schema allow failed request formats to remain reproducible.

The request/response format follows the official [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)
and [Responses API reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create).
The API rejected L1's const-only action discriminators before inference; L2 adds
explicit string types without changing the prompt or action capabilities.

## Budget and timing

The local budget reserves a conservative request-byte-based input allowance plus
maximum output cost before every call. Unknown-usage, pending or interrupted calls
retain that reserve. Known usage replaces it with the estimated token cost. A
call that cannot fit the remaining budget is not sent. The pilot processes episodes
sequentially, so reservation accounting assumes one writer. A new output directory
creates a new budget scope; the operator must account for prior runs.

Rates verified from the [official model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
on 2026-09-11 are $4/M uncached input, $0.40/M cached input and $20/M output tokens.
Estimates are not provider invoices or guarantees against billing adjustments.
The initial $5 envelope includes L1 reservations and its diagnostic; L2 is limited
to $4.50. Report measured API round-trip time separately from simulated action time;
round-trip latency is not isolated model inference time.

## Protocols and validation

- [L1 protocol](protocols/L1.md): initial API integration pilot, including failures.
- [L2 protocol](protocols/L2.md): corrected request format, unchanged model/prompt.
- [L1 source](results/llm_L1_source.zip), [L2 source](results/llm_L2_source.zip).
- [Runner tests](../../tests/test_humanoid_llm.py): input isolation, execution and
  rejection persistence, deadline limits, strict-schema regression, cost accounting,
  budget exhaustion, timeout, unknown usage, refusal and malformed output handling.

The full suite passes 60 tests before L2's live requests. Live model outcomes must
be reported separately from these deterministic infrastructure tests.

See [pilot results](LLM_RESULTS.md) for the completed live outcomes and replay.
After the pilot, replay labels were corrected and the full suite passed 61 tests.
