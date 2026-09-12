# L2 grasp and placement audit

Date: 2026-09-12. This is a post-hoc reading of saved L2 actions/physics, not a new
trial or a prompt revision. All original outcomes remain unchanged.

| Seed | Recorded finding | Consequence |
|---|---|---|
| 700 | The first descent to site Z=0.84 m moved the block from approximately (0.233, −0.187, 0.760) to (0.146, −0.197, 0.725) m before hand closure | The block was displaced during approach; after later closure it finished on the ground without sustained lift |
| 701 | The first descent moved the block from approximately (0.253, −0.166, 0.760) to (0.159, −0.193, 0.725) m before closure | The next lowering request was rejected at 3.5 s, with no sustained lift |
| 702 | A lift and carry completed; after carry the hand site was approximately (0.243, −0.360, 0.934) m while the object center was (0.179, −0.339, 0.923) m | The held object was offset from the site; the subsequent site target (0.244, −0.380, 0.790) m was rejected by the guard |

The first two cases show that failures began before a grasp was established, not
only during basket placement. Commanded grasp-site pose is not a guarantee about
palm/fingertip clearance or object pose. The observation contract identifies the
site as a reference, but does not provide a validated hand/object contact envelope.
The third case demonstrates an actual contact-based lift while retaining a failed
placement outcome. No inference about hidden model reasoning is needed.

The L2 prompt supplied the site orientation convention and stated that targets
are not automatically centered on the object. It did not supply the tuned
conventional offset/release recipe. Future work should separate:

- A clearer geometric/sensor contract available equally to both policies.
- A recipe-assisted prompt, which is a different experimental condition.
- Visual feedback and image-derived pose estimates, which need their own validation.

Do not repair old results or silently add a grasp skill behind the model interface.
[Original attempts](results/llm_L2_attempts.zip), [L2 results](LLM_RESULTS.md),
[visual observation work](VISUAL.md) and [plan](PLAN.md) preserve the evidence.
