# Task 007 review — changes requested

Reviewed tip: `8938222791d542640ebb0f094891e99a8751eb79`.
Base: `87bce15dda8a99b8c8d9ff0bf3c657653a998eba`.
No integration, freeze or C2 experiment is accepted at this revision.

The three archived C1 episode prompts reproduce byte-for-byte, the actual C2
paragraph matches the proposal, and robot-only nominal geometry reproduces the
expected seven collision geoms and bounds. The retained AGY full-discovery log
reports 224 passing tests. Independent review ran all 18 submitted policy tests
with CLI-login and renderer boundaries injected; those pass. No review model
decisions, rendered episodes or physics rollouts were needed for the findings below.

## R1 — High: execution provenance does not match retained evidence

`humanoid_sim/codex_policy.py:627` hashes sorted JSON plus newline, but line 645
writes `geometry_evidence.json` through the unsorted `write_json` serializer.
The actual execute-path digest would therefore disagree with the saved file:

- Recorded: `d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6`.
- Written-file digest: `a62640267f80dd24d91cb0319a4a37711a7ecd38025175830e517c49ae619cb9`.

Geometry evidence is written only after `run_visual_episode` returns. An interruption
can leave a saved episode referencing an absent geometry artifact. Also, the
top-level `prompt_sha256` still comes from the scaffold's bare `VISUAL_PROMPT`:
main supplies no replacement, so it omits both the CLI decision instruction and
C2 paragraph. Per-decision prompt hashes are correct, but do not make that aggregate
claim accurate. The execution metadata also omits the protocol path promised by
the completion report. `git_source_commit()` silently returns `unknown`, and
preflight records HEAD without identifying a dirty implementation.

Required: use one exact serialization for hashing and writing; persist static run
evidence before the first decision and retain it on interruption. Distinguish
complete static instruction hashes from per-decision full prompt hashes, and bind
reports to their actual retained files. Record protocol path and relevant source
hashes/dirty state; never present an unknown or dirty source as a reviewed frozen
execution. Test the production entrypoint with injected simulator/CLI boundaries,
including interruption, rather than just the geometry helper.

## R2 — High: condition and settings validation can be bypassed

`visual_policy_runner.py:683` selects `condition or condition_id`, never compares
both, and validates a protocol only if a recognised condition is present. It does
not compare the callable model/timeout to the labelled configuration. All these
cases reached a sentinel callable in the review (no actual model or action):

1. `condition=c2`, `condition_id=c1`, C2 protocol and a C2 callable.
2. C1 protocol with no condition fields, and a C2 callable.
3. Matching C2 labels and declared `gpt-5.6-sol`, but callable `model=other-model`,
   `timeout=180`.

The CLI probe path additionally bypasses the fixed-model check at
`codex_policy.py:595` and can label an altered-model probe C2.

Required: normalise and validate condition identity consistently at every labelled
entrypoint. Reject conflicting aliases, missing identity that permits relabelling,
unknown labels, protocol/model/timeout/budget mismatches before capture, directory
creation or callable invocation. Preserve generic offline runner injection and
unlabelled historical probes without silently applying C1/C2 claims to them. Add
regressions for these exact cases, including the probe path.

## R3 — Medium: default C1 check regresses and tests require real login/graphics

The original default C1 command performed a local version/login check. The new
default calls `run_preflight`, loads scene/IK, randomises object state and renders
a fresh static image (`codex_policy.py:486–518`). This changes C1 behavior and makes
a previously graphics-free command need graphics. The new preflight unit test
(`tests/test_codex_policy.py:434`) invokes actual `check_install` and `RGBRenderer`;
its success depends on the developer's signed-in CLI and graphics environment.
Review reproduced default `run_preflight` failing when the CLI/login is unavailable.

Required: preserve C1's original default local-check behavior. Prefer a committed
archived public input for C2's payload/preflight demonstration, with explicit
provenance, rather than synthesising a different initial observation. Keep any
optional real installation/graphics diagnostic separate and labelled. Offline
unit tests must inject login/renderer dependencies and fail if a real model
process is attempted; they must run without account credentials or graphics.
No new performance episode or live Codex probe is authorized to fix this finding.

## R4 — High: completion report and retained handoff are inaccurate

`007-completion.md:20–38` quotes text not present in the proposal or implementation,
claims 14 geoms and bounds `[-.05,.05] × [-.07,.07] × [-.17,.01]`, while code and
local evidence have **7 geoms** and the actual C2 bounds
`[-.074,.058] × [-.042,.042] × [-.077,.085]`. The paragraph precedes observation
JSON, not a JSON schema. Other unsupported claims include table-height variation
in tests and 36 related tests (the submitted suites contain 3 audit + 30 runner
tests, i.e. 33). “No network calls” cannot describe a task that pushed a branch;
“simulation was never stepped” cannot describe full simulator unit discovery.
Limit zero-step claims to static preflight and geometry checks.

All five preflight files referenced by hash exist only in the ignored worktree
runtime directory, not the committed handoff. Their `source_commit` is the starting
commit that lacks C2 code. The completion report omits the final tip/code commit.
The C1 comparison command's exit code alone would not prove equality without
`--exit-code` (review independently verified the unchanged artifacts).

Required: rewrite the report from verified final artifacts and commands. Commit a
compact preflight evidence bundle/manifest with file hashes, actual source identity,
and reproducible generation command. Preserve the prior attempt separately; do
not replace historical C1 evidence. Identify exact code and handoff revisions, test
coverage and which checks were independently rerun. Keep C2 unfrozen/unexecuted.

## Revision handoff

Implement fixes on the same AGY branch/worktree, run focused regressions and the
required final checks, commit/push, and return one complete corrected handoff.
Codex will review the revised exact tip. No main merge/push or scientific scope
change is delegated. See retained [reproductions](007-reproduction.json),
[reproduction script](007-reproduce.py) and [injected policy test log](007-policy-tests.txt).
