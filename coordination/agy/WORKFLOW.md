# Antigravity implementation and Codex review

Antigravity (AGY), using the user's Gemini 3.8 Flash configuration, executes bounded
repository tasks. Codex writes the briefs, reviews the code and evidence, and
integrates accepted changes. The user relays prompts and completion notifications;
there is no configured direct agent-to-agent connection.

## Handoff loop

1. Codex writes a numbered task with scope, starting revision, constraints,
   acceptance criteria and required evidence. Status: **ready**.
2. AGY reads the task, creates its dedicated branch/worktree and records its exact
   starting commit. It completes the authorized implementation and development
   checks without asking about routine choices. Status: **in progress**.
3. AGY commits implementation, tests and its completion report on that branch,
   pushes the branch, and returns its name and tip hash. Status: **ready for review**.
4. Codex checks the branch diff, evidence and reproducibility, runs appropriate
   checks, and records a review against that exact commit. Reported success is
   not sufficient evidence. Status: **accepted**, **changes requested**, or **rejected**.
5. For revisions, AGY adds commits to the same branch and updates the report.
   Codex reviews the new tip; acceptance of an older tip does not cover new changes.
6. Codex integrates an accepted tip, updates the experiment checklist and issues
   the next brief. A later fresh experiment gets its own frozen protocol and task.

Only one AGY task is active initially. Keep implementation review separate from
fresh-validation review. Failed experiments are valid deliverables when the
protocol and complete evidence are retained.

## Workspace and permissions

Use a dedicated Git worktree: two applications must not switch branches or edit
files in the same working directory. The normal checkout remains Codex's workspace.
AGY may read the repository, edit its worktree, run local development/tests, commit
and push its task branch. It must not merge or push main, rewrite shared history,
change frozen evidence, access robot hardware or make paid API calls under these
briefs. Additional capabilities can be explicitly authorized in a later task.

Grant graphics access when a brief requires MuJoCo rendering. Use existing locked
dependencies; propose dependency changes with a reason. Keep keys and credentials
out of prompts, reports, logs and commits. Report exact command/permission failures
instead of claiming a check passed. These are project coordination rules, not
claims about Antigravity's own permission enforcement.

The ignored `runtime/` dataset and `.venv/` may exist only in the normal checkout.
A worktree must explicitly identify any reused interpreter or read-only runtime
inputs. It must not mistake missing local artifacts for missing committed code.

## Review checklist

- Does the exact branch diff satisfy the brief without unrelated changes?
- Do policy inputs exclude object truth, scorer feedback and private annotations?
- Are estimates distinguished from hypotheses, stale values and unavailable output?
- Do tests cover meaningful failure/recovery cases, and are reported checks reproducible?
- Are datasets labeled development, frozen validation or post-hoc analysis correctly?
- Are refusals, missing cases and failures retained in their declared denominators?
- Do source revisions, artifacts and reported metrics agree?
- Are limitations and remaining checklist items accurate?

## Task register

| Task | Status | Branch | Scope |
|---|---|---|---|
| [001](tasks/001-reacquisition.md) | [Changes requested: evaluator R2](reviews/001-review-r2.md) | `agy/001-reacquisition` | Implement and develop temporal reacquisition; propose fresh protocol, do not execute it |

Use the [completion template](reports/TEMPLATE.md) and [review template](reviews/TEMPLATE.md).
The experiment's [living checklist](../../experiments/humanoid-pick-place/PLAN.md)
remains the source of truth for scientific progress.
