# AGY task 011 — Operate frozen C3 and package evidence

Status: ready for one execution after the freeze/brief are committed.
Branch: agy/011-c3-execution. Worktree: /private/tmp/mujoco-llms-agy-011.
The user asked to continue after Task010 acceptance. Codex authorizes the single
frozen C3 run in protocols/C3.md; AGY owns operation/packaging, Codex owns every
VLA decision and interpretation. Use the primary existing .venv, no new dependencies.

## Establish frozen inputs

- [ ] Read C3.md, C3_FREEZE.json, C3_PROPOSAL.md and Task010 acceptance.
- [ ] Confirm clean task worktree at the exact launch commit, local CLI 0.154.0 and
      ChatGPT login. No API endpoints/keys or model probes. Compare every frozen
      file digest and instruction/runtime-schema/geometry digest before starting.
- [ ] Create ignored runtime/humanoid/codex-C3/manifest.json in a new run root with
      source commit/clean state, freeze/protocol/task hashes, full pinned file map,
      local CLI/config info, seed [820], one requested trial and all budgets.
      Do not edit tracked files until the episode exits. Preserve precondition
      failures and stop; no repairs to the controller/protocol are authorized.

## Execute once

- [ ] Execute the exact C3.md command ONCE. Graphics and signed-in CLI access,
      subprocess execution and automatic AGY permissions are authorized.
- [ ] Save stdout/stderr and exit status; monitor process completion. No simulator
      intervention, decision editing, fallback, retry, extra episode or live probe.
      No AGY/Gemini VLA decision, private input injection or held-out seed use.
- [ ] A guard rejection or model failure is a result. Preserve it and stop execution.

## Package after exit

- [ ] Verify all frozen file hashes still match. Preserve every runtime file,
      including failed/partial decisions, launch logs, source manifest, static files,
      public images/requests, CLI events/stderr/raw output and private score/trajectory.
      Create results/codex_C3_episode.zip with a full member SHA-256 manifest.
- [ ] Verify every prompt/PNG via public_input(condition='c3'), every completed event
      stream against its full response, and only-command forwarding. Missing/malformed
      outputs remain explicit records, not discarded cases. Record real invocation
      counts separately from unobservable network requests; do not claim zero tokens.
- [ ] Prepare machine-readable results/codex_C3.json with scorer/runner outcomes and
      per-call assessment accounting. Do not invent visual labels or interpretation.
      Keep interpretation as pending Codex review. Do not rerun any physics for analysis.
- [ ] Create coordination/agy/reports/011-blind-images.json containing ONLY ordered
      call numbers, observation IDs, times, PNG paths, image hashes and availability;
      no commands, model assessments, private coordinates or physical outcomes.
      Point to committed archived PNG member names and runtime image paths. Include
      all attempted calls, explicitly flag missing image files. Do not alter images.
- [ ] Write 011-completion.md with provenance, command and checks. Defer scientific
      interpretation/result narrative and final PLAN status to Codex after blind review.
- [ ] Commit/push ONLY the task branch; no source fixes, main merge/push or history
      rewrite. Return exact tip and blind-image index path ONLY, without outcomes,
      assessment values, action descriptions or private metrics in the handoff.

No software/full-suite run is needed: code was independently verified in Task010.
Verify hashes/accounting and git diff --check. If anything requires a code change,
retain the failed attempt and return for review instead of altering/retrying the run.
