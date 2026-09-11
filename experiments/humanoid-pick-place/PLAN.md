# G1 humanoid pick and basket experiment

Started: 2026-09-11. Current scope: supported-body conventional mechanics.

Scene, controller, scoring, persistence, and replay are implemented. The final
mechanical matrix achieved 96/100 task successes and 92/100 strict passes; the
95/100 qualification gate remains open. [Results and retained failures](RESULTS.md).
LLM integration, vision evaluation, free-standing balance, and walking are pending.

## Research question

Can a vision-capable LLM use camera observations, language, and proprioception
to choose successive hand actions that make a humanoid pick the requested object
and place it in a basket? Measure visual action control separately from invoking
a prebuilt pick-and-place skill. Keep the lower-level controller identical across
matched conventional and LLM conditions.

## Implementation sequence

1. Vendor a pinned G1 model with hands; build and inspect a fixed-pelvis scene.
2. Validate physical grasp, lift, transport, release, and independent basket scoring.
3. Establish a conventional exact-state baseline across 100 randomized starts;
   require at least 95 complete successes. Preserve all failures.
4. Add LLM exact-state trials using bounded hand movement and closure primitives,
   initially pausing physics during model calls. Do not give the model an
   automatic pick-and-place tool in the primary experiment.
5. Add camera-only object observations, with proprioception and declared contact
   sensors; separate public observations from scorer truth. Compare conventional
   vision and LLM vision using equivalent motion capability.
6. Implement free-standing balance beneath the action interface. Revalidate
   conventional reach and grasp before comparing LLM policies. Report supported
   and free-standing results separately.
7. Run continuous physics during model requests. Timestamp observations, expire
   stale commands, hold safely on timeout, and measure model/orchestration latency.
8. Freeze held-out scene/instruction conditions and compare exact-state and visual
   baselines, LLM variants, recovery, latency, cost, and episode-level uncertainty.
9. Add walking and carrying only after stationary free-standing manipulation passes.

## Revised mechanical protocol frozen for the third 100-trial matrix

- One G1 with fixed pelvis, one right hand, one free red block, one static basket.
- Robot arm begins in an IK-generated overhead ready pose. This is an initialization
  assumption, not a demonstrated transition from the standard standing posture.
- Block dimensions: 5 × 7 × 12 cm, mass: 60 g. Table top: 0.70 m.
- Nominal block center XY: (0.24, −0.18) m. Independently randomize X and Y by
  ±1.5 cm and yaw by ±0.15 rad using NumPy's seeded generator.
- Basket center XY: (0.18, −0.36) m. Interior: 17 × 17 cm. Floor top:
  0.712 m. Rim top: 0.84 m. Basket location is fixed in this milestone.
- Development seeds: 0–19, plus the two failed mechanical matrices (100–199 and 200–299).
  Revised mechanical validation seeds: 300–399. No policy modifications or
  selective retries within any 100-trial matrix. Earlier runs are retained
  in `results/mechanical_v1.json` and `results/mechanical_v2.json` with source archives.
  The wider block is a task-design change, so the revisions are not a controlled
  comparison on identical task geometry.
- Exact-state controller: use a +1.5 cm world-X hand-site offset to keep the palm
  clear of the block, align above object, descend, close, lift, hold 0.5 s,
  carry at hand-site Z = 0.975 m, transport to (0.19, −0.36) m, lower to
  Z = 0.86 m, open, retract, hold 8 s. All movement/hand actions
  use 2 s. Normal completed duration: 25 simulated seconds including reset settling.
- Physics: 1 ms timestep, implicitfast, 50 iterations. Contact and hand overrides
  are documented in `models/g1/SOURCE.md`; object state is only set at reset.
- Each trial runs sequentially, faster than real time. No LLM, no walking, no
  balance controller, and no concurrent video rendering during the matrix.

## Independent scoring

Scoring receives actual physics state and contacts, never action intentions.

A sustained lift requires the object's lowest point to exceed the table by 4 cm
while touching the right hand for at least 0.2 s. After that, success requires:

- The object's full world-axis bounding box inside the basket interior, including
  its top below the rim; allow 0.5 mm contact penetration tolerance.
- Direct contact with the basket floor and no right-hand contact.
- Linear speed below 2 cm/s and angular speed below 0.15 rad/s.
- Grasp site at least 12 cm from the object's center.
- All placement conditions sustained for 2 s; revoke arrival if they cease.

A gate success additionally requires no controller exception and maximum object
contact penetration at most 2 mm over the entire episode. The gate requires
95/100 or more such successes. Individual failures, early stops, and quality
failures remain in the denominator. This is a narrow mechanical development gate,
not a formal LLM benchmark or a physical-robot validation.

## Later evaluation

Compare conventional exact-state, LLM exact-state, conventional vision, and LLM
vision with matched seeds and action limits. Report task success, wrong-object
rate, grasp and placement failures, falls, recovery, wall-clock latency, action
counts, and cost per success. Use independent evaluation sessions and preserve
all API/runtime failures. Record provider-returned model identity and request
telemetry rather than attributing interactive session timing to inference alone.

The previous SO101 experiment established why this separation matters: correct
selection did not ensure timely physical execution, and concurrent workloads
confounded some later model comparisons.
