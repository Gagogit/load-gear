# Agent Protocol
Schicht: B
Letzte Aktualisierung: 2026-02-27

## Work Cycle

1. Read CLAUDE.md (always loaded)
2. Open `/docs/tasks/backlog.md`, find next open task
3. Open the task file (e.g., `task-003.md`)
4. Load ALL documents listed in the task's "Lade:" section
5. Execute the task following its steps and acceptance criteria
6. Document decisions and rationale in STATUS.md
7. Check off the task in backlog.md
8. Return to step 2

## Decision Documentation (STATUS.md)

After each completed task, add an entry:

```
## Task-003: [Task Title]
- Decision: [What was decided]
- Rationale: [Why this approach]
- Impact: [What this affects downstream]
- Open: [Any unresolved questions for review]
```

## Phase Boundary Protocol

At the STOPP marker in backlog.md:

1. Write final STATUS.md entries
2. Copy STATUS.md content → `/docs/status/phase-{n}-complete.md`
3. Clear STATUS.md (keep header, reset to empty)
4. STOP — do not proceed to next phase
5. Wait for human approval

## Review Tasks

Review tasks (suffixed with `r`, e.g., task-002r):
- Load only architecture overview + STATUS.md
- Compare implementation against target architecture
- Check for: contradictions, forward-blockers, undocumented decisions
- If issues found: create fix-task and insert before next regular task in backlog

## Backlog Updates

- Check off completed tasks: `[x] task-003.md — Description`
- Insert fix-tasks immediately after the current position
- Never reorder existing tasks
- Never skip ahead past a STOPP marker

## Error Protocol

When a task cannot be completed:
1. Document the blocker in STATUS.md
2. Do NOT attempt ad-hoc fixes outside the task scope
3. Create a fix-task with clear description of the problem
4. Insert fix-task into backlog before the next regular task
5. Mark current task as blocked (not completed)

## Context Rules

- Never assume knowledge from a previous task — only trust loaded documents
- If a task seems to conflict with architecture, flag it — don't silently resolve
- If acceptance criteria are ambiguous, choose the safer/simpler interpretation
- Every file you create or modify must be traceable to a task requirement
