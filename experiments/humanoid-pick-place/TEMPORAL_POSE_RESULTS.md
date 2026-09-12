# P4 temporal RGB/hand-motion results

Date: 2026-09-12. **The candidate returned accurate centers on 14/20 nominal
post-warmup targets, but failed the frozen 16/20 coverage screen.** Accepted errors
averaged 3.645 mm, maximum 7.420 mm. No accepted original center exceeded 20 mm.
No position was emitted on release/retract or either altered transport image type.
The candidate remains disconnected from control.

## Frozen trajectories and accounting

The [P4 protocol](protocols/P4.md) was frozen before seeds 820–829. Ten exact-state
G2 driving episodes completed without failures. All 120 reset/action-endpoint
captures preserved full integration state exactly. The estimator ran offline on
six endpoints per episode: lift, lift hold, transport, lower, release and retract.

There are 60 original observations, of which 40 are carried views. The first two
carried views per episode are warmup/low-motion observations; transport and lower
are the 20 nominal post-warmup targets. Those targets stay in the denominator even
when an earlier refusal clears history. No missing or difficult case was excluded.

| Original endpoint | Observations | Accepted within 20 mm | Refusal |
|---|---:|---:|---|
| Lift | 10 | 0 | 10 insufficient history/motion |
| Lift hold | 10 | 0 | 10 insufficient history/motion |
| Transport | 10 | 7 | 3 inconsistent rigid transforms |
| Lower | 10 | 7 | 3 rewarming after transport rejection |
| Release | 10 | 0 | 10 inconsistent rigid transforms |
| Retract | 10 | 0 | 10 rewarming after release rejection |

Thus useful-center coverage is **14/20 (70%)** on nominal post-warmup targets and
**14/40 (35%)** on all carried endpoints. Neither number is physical task success.
The 20 mm exploratory screen is not a validated grasp or release tolerance.

## Loss and sensor inconsistency

Two additional tracker streams alter only the transport image in each episode:
a black image, or the preceding lift-hold RGB with the current hand pose/time/ID.
All later frames return to normal. These streams reuse the 60 original frames and
introduce only 20 altered sensor frames. The 180 total responses are correlated;
they are not 180 independent episodes or physical slip trials.

| Stream | Responses | Positions emitted | Altered transport positions | Release/retract positions |
|---|---:|---:|---:|---:|
| Original | 60 | 14 | Not applicable | 0/20 |
| Black transport | 60 | 0 | 0/10 | 0/20 |
| Frozen transport RGB | 60 | 0 | 0/10 | 0/20 |

The black-transport stream produced 10 insufficient-boundary, 10 model-mismatch
and 40 history/motion refusals. The frozen-image stream produced 20 model-mismatch
and 40 history/motion refusals. History resets prevented stale/extrapolated output,
but neither stream reacquired a useful carried center before release in this test.
This is loss containment, not demonstrated recovery or general stale-image detection.

The private audit deliberately gave no release action hint. An acting wrapper
should invalidate the tracker on known release rather than rely on this diagnostic.
Real release/retract observations challenge a broken hand/object relationship;
synthetic image corruption does not establish physical slip detection.

## Rigid-model validity

The [development drift measurements](results/temporal_development.json) showed
7.7–25.0 mm of center displacement relative to the hand across seeds 740–742.
Fresh P4 episodes had 3.30–8.25 mm from lift to lower. The maximum true center drift
within an accepted P4 window was 3.723 mm. These private values were computed after
estimation and never supplied as corrections or acceptance inputs.

Seeds 820, 825 and 828 failed at transport with worst-frame fit RMS 1.160, 0.974
and 1.035 px, above the fixed 0.75 px threshold. Clearing their history left lowering
in warmup. A model mismatch is not a unique slip diagnosis: rotation changes,
segmentation/occlusion and optimizer limitations can also contribute.

The analytic rigid positive controls verify the geometric optimizer separately:
its best tilted-control center and selected axis-aligned-control center are both
within 2 mm. These controls use exact projected boundaries rather than rendered
pixels; they do not prove the entire RGB pipeline works or that a real grasp is rigid.

## Post-hoc comparison on the same images

After freezing P4, the unchanged P3 estimator was also run on its 40 original
carried images. This comparison was not part of the preregistered P4 screen and
did not change any thresholds or outputs.

| Same 20 transport/lower images | Within 20 mm | Accepted mean / max error |
|---|---:|---:|
| P3 single-frame candidate | 13/20 | 11.717 / 15.073 mm |
| P4 temporal candidate | 14/20 | 3.645 / 7.420 mm |

Accepted subsets differ. On the seven targets accepted by both, mean error was
10.462 mm for P3 and 4.692 mm for P4. This is a small development comparison, not a
formal significance result. P3 accepted 19/40 across all four carried endpoints;
P4's required motion history intentionally withholds the first two endpoints.

## Validation and source versions

The frozen P4 implementation passed **83 tests**. After the audit, review found
that an unparseable or missing timestamp/ID could raise before clearing history.
A small metadata-validation fix and regression were added after preserving the
frozen source archive. The current suite passes **84 tests**. The patch changes
malformed-input handling only; fitting, thresholds and valid-observation behavior
are unchanged. P4's numeric results refer to the archived pre-hardening source;
the physical audit was not repeated for that input-validation patch.

Diagnostic estimator time across the original sequence averaged 1.429 s per
response, maximum 4.036 s; warmup responses are included. Local concurrent work
and optimization affect these timings. This is not a real-time control benchmark.
No model/API calls or image-driven actions were made.

## Next step

Keep P4 frozen and disabled. Develop explicit reacquisition after a model mismatch:
a fresh current frame can seed a new relationship, followed by enough new motion
evidence to test it. Do not reuse an old center as a measurement or assume that
reacquisition confirms a rigid grasp. Test natural slip/loss and recovery on new
trajectories, with the extra observations/actions counted against the task budget.
Only then integrate a conventional RGB controller and qualify full physical episodes
before a matched visual LLM comparison.

## Artifacts

- [All temporal responses and frozen hashes](results/temporal_P4.json).
- [Private capture records](results/temporal_P4_capture.json).
- [Post-hoc P3 matched-image records](results/temporal_P4_single_frame_comparison.json).
- [Frozen source, protocol, tests and development scripts](results/temporal_P4_source.zip).
- [Frozen 83-test log](results/temporal_P4_tests.txt),
  [current 84-test log](results/temporal_P4_current_tests.txt),
  [post-audit metadata hardening patch](results/temporal_P4_metadata_hardening.patch).
- [Method and run guide](TEMPORAL_POSE.md), [living checklist](PLAN.md).

RGB, public observations and saved trajectories remain locally under
`runtime/humanoid/temporal-P4/capture/` (ignored by Git). The source archive includes
representative development fixtures and uses the repository's pinned G1 mesh assets.
The stored private results are evaluator evidence, not policy-accessible inputs.
