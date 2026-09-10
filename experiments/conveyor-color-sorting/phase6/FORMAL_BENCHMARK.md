# Remaining formal benchmark

The 24-case Phase 6 development matrix checks implementation and exposes failure
modes. It does not complete the larger evaluation proposed in the original plan.
This document preserves the remaining work without silently treating development
trials as a formal benchmark.

## Prerequisites

- Support 20-cube streams with reproducible spawning and complete identity/outcome accounting.
- Expose repeated timestamped image observations and versioned actions to an automatic model runner.
- Record exact model configuration, prompts, responses, token usage, tool calls, and cost where available.
- Freeze orchestration and concurrency; validate runtime headroom before scored runs. The Phase 6 development run exceeded its lag limit in seven episodes; recording also overlapped the final live trials.
- Separate development and evaluation sessions, hide scoring configurations from the agent, and reserve unseen seeds and instruction variants.
- Validate mid-motion instruction changes if they are included; Phase 6 only changed rules before the first eligible approach.

## Proposed trial design

Start with 30 episodes of 20 cubes per main condition and controller. Treat this
as a starting sample size, not a completed power analysis. Counterbalance target
color and arrival position, match initial cube sequences across controllers, and
vary one robustness factor at a time. Predeclare a primary outcome and minimum
meaningful difference before deciding how many conditions to include.

Compare conventional exact state, LLM exact state, conventional vision, and LLM
vision with equivalent motion capabilities. Include single-color reference rules,
instruction changes, multi-color rules, and counting. Give the conventional
baseline a documented supported grammar; assess unseen language separately from
physical execution so a parser's unsupported wording does not masquerade as a
mechanical failure.

## Scoring and analysis

Record every spawned cube, destination, unintended contact, expired request,
rule version, and response delay. For changing rules, fix eligibility at a
predeclared physical boundary or commitment event independent of requested
actions. Define count consumption even when a target is missed. Preserve every
failure and predeclare how runtime-health failures affect timing conclusions.

Report per-condition rejection and wrong-rejection rates, throughput, adaptation
delay, and cost. Use episode-clustered uncertainty and matched comparisons; cubes
within an episode are not independent observations. Separate end-to-end response
time from model inference time if the runner provides both. Do not generalize
simulation results to physical SO101 performance without separate hardware tests.

Status: **not executed**. Existing development evidence remains under
[Phase 6](../PHASE6.md); the [main checklist](../PLAN.md) tracks this milestone.
