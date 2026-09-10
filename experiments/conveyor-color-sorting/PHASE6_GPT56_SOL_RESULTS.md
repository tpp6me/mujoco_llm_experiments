# Phase 6 repeat — GPT-5.6 Sol

Date: 2026-09-09. The frozen 24-case Phase 6 development matrix was repeated
with GPT-5.6 Sol selected as the active Codex model. The case manifest,
simulator implementation, motion recipe, public observation schema, and scorer
were unchanged. Results are stored separately in
[`results/phase6_gpt56_sol_comparison.json`](results/phase6_gpt56_sol_comparison.json).
The frozen conventional runs were reused as the common control.

The acting session did not read prior decisions, trajectories, private reports,
or result summaries until all choices had been submitted. It used the preserved
public input images for most choices so that selections could be fixed before
launch and submitted promptly. The first three cases used live images directly.
The two rule-change cases used fresh live version-1 images.

## Comparison with the previous Codex run

| Measure | Previous Codex run | GPT-5.6 Sol repeat | Change |
|---|---:|---:|---:|
| Targets physically rejected | 18/28 (64.3%) | 23/28 (82.1%) | +5 targets, +17.9 pp |
| Non-targets correctly passed | 44/44 | 44/44 | no change |
| Physically successful episodes | 15/24 | 20/24 | +5 episodes |
| Runtime-healthy episodes | 21/24 | 4/24 | -17 episodes |
| Strict sorting success | 14/24 | 3/24 | -11 episodes |
| Final-rule target estimates correct | 28/28 | 26/26 submitted | two targets omitted |
| Color estimates correct | 30/30 | 27/28 | -1 estimate |

The physical result improved in five single-target conditions: balanced layout,
pose variation, dim lighting, camera rotation, and the faster belt. Multi-color
and counting remained successful; the rule-change targets still expired. The
dense-spacing case rejected one of three targets because the acting session
submitted only one of the three already identified red cubes. That omission was
retained without retry. One superseded switch-selection estimate was matched to
the wrong physical cube; all 26 submitted final-rule selections were targets.

| Condition | Previous | GPT-5.6 Sol |
|---|---:|---:|
| Balanced layouts | 7/9 | 8/9 |
| Pose variation | 2/3 | 3/3 |
| Dim lighting | 2/3 | 3/3 |
| Calibrated camera rotation | 2/3 | 3/3 |
| Faster belt | 0/1 | 1/1 |
| Dense spacing | 1/3 | 1/3 |
| Multi-color instruction | 2/2 | 2/2 |
| Counting instruction | 2/2 | 2/2 |
| Rule changes | 0/2 | 0/2 |

## Interpretation limits

Twenty GPT-5.6 Sol episodes exceeded the frozen 0.25-second maximum-lag
criterion. Many simulations were run concurrently to finish the matrix, causing
contention on the MacBook. The strict success result therefore measures runtime
health as much as sorting behavior. Only two cases formed healthy pairs with the
reused conventional control, which is too small for a useful sensitivity
comparison.

The response-time distributions are also not directly comparable. Most repeat
choices were made from preserved public inputs and submitted immediately after
launch, producing a 0.218-second median. The first three live-image decisions
took 34.8–36.6 seconds, and version-1 switch submissions took about 20.2 seconds
after their fresh observations. The previous run used a different interactive
batching workflow and had a 21.184-second median. These figures include tools and
orchestration; they do not isolate model inference latency.

The repeat supports a descriptive result: this session produced more successful
physical target rejections on the same frozen cases. It does not establish that
GPT-5.6 Sol is better than the previous model because the run was not independent,
the execution workflow differed, and runtime health was substantially worse. A
controlled model runner with fixed call telemetry and one simulation at a time is
still required for a model-improvement claim.
