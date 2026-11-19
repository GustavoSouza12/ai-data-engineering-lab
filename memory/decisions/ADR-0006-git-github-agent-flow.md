# ADR-0006 — Git and GitHub flow with agents

- Date: 2026-11-19
- Status: accepted on 2026-11-19 (private remote created with the user's authorization)
- Partially supersedes: D-004 (pull requests exist once an authorized remote exists; merge stays human-only)

## Context
The user wants to see the full cycle: features on branches, agent commits, tests, review and human approval on GitHub. The architecture asks for "everything through PRs" and a protected `main`.

## Decision
Per feature:
1. The coordinator proposes the scope in `memory/TASKS.md`; the user approves in the conversation.
2. The coordinator creates the `feature/<id>-<topic>` branch from `main`.
3. The builder implements, runs the tests and commits **only on that branch**. It does not push, switch branches or touch `main`.
4. The coordinator produces `git diff main...<branch>` and hands it to the reviewer and governance agents in parallel (they have no shell).
5. The coordinator consolidates the reports. Serious findings go back to the builder.
6. With the user's approval, the coordinator pushes and opens the PR with the consolidated report.
7. CI runs on the PR (from F0.3 on).
8. **Merge only by the user, on GitHub.**

Other points:
- Default branch renamed from `master` to `main`.
- Private remote repository.
- Everything published to GitHub (code, docs, commit messages, PRs) is in English and carries no tool attribution (T-027).

## Consequences
Agent commits are traceable per branch. The guarantee that the builder does not push or merge is an instruction, not a technical block; governance checks it on every review.
