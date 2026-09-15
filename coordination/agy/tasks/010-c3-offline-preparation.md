# AGY task 010 — Offline preparation of explicit visual assessment (C3)

Status: accepted and integrated; see [Codex acceptance](../reviews/010-acceptance.md). No live experiment authorized.
Owner: AGY implements/tests/packages; Codex plans, reviews, and makes all VLA decisions.
Use a dedicated `agy/010-c3-offline-preparation` branch/worktree from the main commit
containing this brief. Record that exact starting commit.

Read the [C3 proposal](../../../experiments/humanoid-pick-place/protocols/C3_PROPOSAL.md)
and Task 009 acceptance. Implement only the proposed response-contract intervention:
a two-field visual assessment plus the existing command in a single signed-in Codex
CLI response. The proposal's text, labels, boundaries and budgets are authoritative.
Do not invent additional task instructions, geometric advice or a grasp recipe.

## Deliverables

- [x] Add opt-in `c3` beside unchanged/default `c1` and existing `c2`. Preserve
      historical full prompt bytes and immutable evidence for both prior conditions.
      Build the C3 instruction using exactly the replacements/appendix in the proposal.
- [x] Define the strict response schema and validation. Reject missing/extra fields,
      invalid labels and malformed commands. C3's full response is retained and
      checked against CLI event output; only its validated `command` reaches the
      unchanged interface. No assessment-based veto, rescue, coordinate substitution,
      extra model call or silent fallback. A validation failure stays a counted stop.
- [x] Retain assessments with image identity, time, full prompt hash, schema hash,
      requested model/configuration and source identity. Keep static-instruction
      hashes distinct from full per-decision prompt hashes. Never add assessments
      or private evaluator annotations to subsequent public policy history.
- [x] Preserve 20 decisions, simulated t=25 seconds, 120 seconds per invocation,
      fresh isolated CLI sessions and current tool/credential boundaries. Keep
      ChatGPT login and requested `gpt-5.6-sol`/low reasoning. Local CLI version/login
      checks are allowed; if version differs from 0.154.0, report it for review
      without changing the proposal or making a model request.
- [x] Add meaningful offline tests: exact C1/C2 prompt preservation, exact proposed
      C3 text/schema, valid assessment retention with unchanged command forwarding,
      malformed response failure accounting, interruption evidence, no extra calls,
      no assessment leakage into later history, and condition/provenance isolation.
      Use injected process/renderer/interface doubles; no reset or physics stepping.
- [x] Generate an offline preflight using committed public observations and stubbed
      CLI outputs, clearly labelled synthetic software checks. Record all script,
      schema, instruction and artifact hashes after the final source edits. Do not
      label fixture outcomes as model judgments or performance measurements.
- [x] Run affected tests once after fixes, preserve their logs, update the living
      plan and runner documentation, and write `coordination/agy/reports/010-completion.md`.
      Use the existing interpreter/dependencies. Run `git diff --check BASE..HEAD`.
- [x] Commit/push only the task branch and return the exact handoff tip. Stop for
      Codex review; do not freeze or execute C3, merge main, probe a model, call an
      API, modify historical evidence, or use held-out seeds 840–849.

Codex will review implementation and decide whether to freeze a separate C3 run.
This task authorizes preparation only. P5's 5.0 mm mean gate remains unchanged.
