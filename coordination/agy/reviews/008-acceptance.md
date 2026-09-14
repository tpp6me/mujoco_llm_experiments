# Task 008 acceptance — C2 evidence, failed manipulation outcome

2026-09-14. Accepted AGY tip: `5ddcd61a55ab4c39d8494fc81e45e49df9ba741f`.
Original evidence commit: `2b97232b4e8dcb991500cf70d5b507dfca1a341b`.
Frozen execution source: `a675e5223a7966926744624561d2e4542883d17a`.

The one authorized C2 episode executed and is fully accounted for: **0/1 placements,
0/1 sustained lifts, 0/1 strict passes**. Nine signed-in Codex CLI invocations
produced nine valid commands; eight executed and the ninth failed IK reachability
before any physics advance. Final simulated time was 7.70 s including reset.
Peak object penetration was 5.184672 mm, above the unchanged 2 mm quality gate.
Acceptance concerns evidence integrity and task completion, not controller quality.

## Independent verification

- Reconstructed all nine full prompts and PNGs byte-for-byte from retained public
  requests using `public_input(..., condition='c2')`; static instruction and geometry
  hashes match the freeze. No private evaluator state was passed to decisions.
- Validated every CLI event log with the pinned parser and matched its completed
  command to the runner record. Zero observed tool items; nine CLI invocations
  are not a claim about internal network request counts. ChatGPT login was used
  without direct API integration, API keys or AGY choosing VLA actions.
- Verified all 73 runtime files against the ZIP member manifest and the original
  runtime bytes, with no missing/extra members or duplicate ZIP entries. Archive
  SHA-256: `940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8`.
- Verified clean frozen execution provenance and unchanged source/protocol hashes.
  Task 008 changes only reports, checklist/index and new evidence; historical C1
  evidence, physics, guards, scorer and thresholds remain unchanged.
- Recomputed action counts, scorer outcomes, zero time advance on rejected action,
  and latency: 224.892082 s summed CLI latency, 24.988009 s mean. Runner latency
  includes a small adapter overhead and is separately 224.910482 s.
- Recomputed CLI-reported token totals: 103,072 input including 5,888 cached;
  4,968 output including 4,480 reasoning. Backend snapshot identity remains
  unverified; the requested model is `gpt-5.6-sol`.
- Independently read the 241 saved qpos samples and action endpoints. Action four
  displaced the object 154.269491 mm in XY and rotated it about 166.58 degrees
  between endpoints. It reached floor height by the end of action five. These are
  sampled post-hoc positions/orientations, not reconstructed force measurements.

The [retained check](008-independent-check.py) and [output](008-independent-review.json)
cover prompts, source, accounting and complete archive verification. From the
repository root with the preserved Task 008 runtime directory:

```sh
.venv/bin/python coordination/agy/reviews/008-independent-check.py --worktree /private/tmp/mujoco-llms-agy-008 --output /private/tmp/c2-independent-review.json
```

No additional model decisions, reset, physics stepping or redundant software test
suite was used for this evidence-only review. Task 007's accepted implementation
validation remains applicable. The complete revision diff passes whitespace checks.

## Review corrections and interpretation

AGY corrected its prose token arithmetic, distinguished IK rejection from collision
checking, and labelled 25.51 N as the scorer's force **at peak penetration**, not a
separately maximized force. The recorded maximum object bottom is 9.47 mm above
its table height; this does not meet the sustained-lift criterion. Raw JSON and ZIP
were already correct and are unchanged by the documentation revisions.

C2 reached more executed actions than C1 but did not demonstrate better task
performance. The damaging approach still displaced the object, after which commands
continued at the old region. The ninth public image shows the red block below the
table edge. Neither command JSON nor qpos reveals the model's internal belief.
The single reused development seed and bundled instruction additions do not support
causal or statistical improvement claims.

All five user-requested stages are complete: AGY revisions, Codex review, C2 freeze,
AGY operation with Codex VLA decisions, and evidence packaging/outcome review.
Next: [Task 009](../tasks/009-c2-failure-audit.md), an offline audit of the damaging
approach and retained visual feedback. Codex will use it to choose a testable
successor condition. No additional trial is frozen or launched here; P5 remains
separate with its unmet 5.0 mm gate and seeds 840–849 unused.
