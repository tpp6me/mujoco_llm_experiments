# Antigravity implementation and Codex review

**Current direction (2026-09-14): AGY handles implementation and operations;
Codex handles planning, review and all VLA decisions.** AGY delegation is restored.
Direct OpenAI API transport remains cancelled. See [execution policy](../EXECUTION_POLICY.md).

Antigravity (AGY), using the user's Gemini 3.8 Flash configuration, executes bounded
repository tasks. Codex writes the briefs, reviews the code and evidence, and
integrates accepted changes. Codex can launch the installed `agy` CLI directly
in dedicated worktrees, inspect its execution logs, and resume a specific
conversation for revisions. The user has
authorized batch runs with automatic permissions within each task brief.

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

To minimise Codex development usage, AGY should complete its own debugging and
required checks before handoff, submit concise evidence with exact paths/hashes,
and address review findings on the same branch. Codex reviews substantive
milestones rather than every edit. AGY can monitor long-running jobs and prepare
reports; a later explicit task may authorize operating the frozen Codex VLA harness.
The VLA decision sessions remain fresh, public-input-only Codex sessions; AGY must
never make or repair model decisions. Codex chooses scientific next steps after review.

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
| [001](tasks/001-reacquisition.md) | [Accepted; integrated](reviews/001-acceptance.md) | `agy/001-reacquisition` | Implement and develop temporal reacquisition; propose fresh protocol, do not execute it |
| [002](tasks/002-reacquisition-evidence.md) | [Accepted; integrated](reviews/002-acceptance.md) | `agy/002-reacquisition-evidence` | Test additional fresh-view evidence on development trajectories; no fresh P5 run |
| [003](tasks/003-p5-preparation.md) | [Accepted with integration fixes](reviews/003-acceptance.md) | `agy/003-p5-preparation` | Prepare revised passive P5 protocol and runner on existing development inputs; no held-out execution |
| [004](tasks/004-visual-policy-scaffold.md) | [Accepted with integration fixes](reviews/004-acceptance.md) | `agy/004-visual-policy-scaffold` | Offline RGB-to-action loop with injected stub; no live provider or fresh P5 run |
| [005](tasks/005-visual-provider-adapter.md) | [Accepted with integration fixes](reviews/005-acceptance.md) | `agy/005-visual-provider-adapter` | Responses image adapter with injected offline transport and unfrozen pilot draft |
| [006](tasks/006-visual-live-transport.md) | Cancelled by user before implementation | `agy/006-visual-live-transport` | HTTPS transport, persistent spending controls and pilot preflight; mocked execution only |
| [007](tasks/007-c2-implementation.md) | [Launched; awaiting handoff](reports/007-launch.md) | `agy/007-c2-implementation` | Implement C2 selection, provenance and offline checks; no model decisions or fresh performance episodes |

Use the [completion template](reports/TEMPLATE.md) and [review template](reviews/TEMPLATE.md).
The experiment's [living checklist](../../experiments/humanoid-pick-place/PLAN.md)
remains the source of truth for scientific progress.
