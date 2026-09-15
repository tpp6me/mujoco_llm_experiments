# AGY task 009 — Launch checkpoint

Date: 2026-09-15. Status at launch: in progress, not yet reviewed.

- Task: [009 offline C2 audit](../tasks/009-c2-failure-audit.md).
- Exact starting commit: `d125d74be4324dad9b938adcd4ef4ded84a2d636`.
- Branch/worktree: `agy/009-c2-failure-audit`, `/private/tmp/mujoco-llms-agy-009`.
- Conversation: `c1f5bc25-a258-4d6c-9ca1-360e76113656`.
- Launch: 2026-09-15 00:50:14 UTC; worker PID 35652, AGY PID 35653.
- Logs/prompt/lifecycle: `/private/tmp/agy-009-execution/` (`prompt.txt`,
  `output.jsonl`, `stderr.txt`, `cli.log`, `status.json`).
- Automatic permissions authorized by the user and scoped by the task; 30-minute
  batch timeout. Exit status alone does not establish task completion or acceptance.

Only offline audit code, local tests, existing-image composition, documentation
and task-branch commit/push are authorized. No physics stepping/reset, new VLA
call, live API/probe, frozen evidence changes, or AGY main merge. Codex reviews
measurements and visual interpretation before specifying a successor experiment.

## First handoff and revision

Initial execution exited normally at 2026-09-15 00:58:05 UTC, handoff
`78511286eace3d7fa0875941497ba40eed1d2907`. Eight focused tests independently
passed; [review](../reviews/009-review.md) requested R1–R4 corrections. Revisions
resume the same conversation/worktree under `/private/tmp/agy-009-revision-r1/`.
No task integration or additional experiment is authorized before acceptance.

## Final acceptance

Revisions completed at `97f1b2c33d2773f9f32b7588500e8ae59a785261`, after
`c5af1af2b61b395f6459ec31cdcddfdafb7e65b3` and a final provenance correction.
Second revision logs are in `/private/tmp/agy-009-revision-r2/`; AGY exited with
code 0 at 2026-09-15 01:37:47 UTC. [Acceptance](../reviews/009-acceptance.md)
records independent tests, artifact reproduction and Codex visual interpretation.
Task 009 is integrated; no live episode occurred. Task 010 is prepared, not launched.
