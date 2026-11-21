# ADR-0016 — Firstmate as agent runtime

- Date: 2026-11-21
- Status: accepted (decided by the user on 2026-11-21)
- Amends: ADR-0006 (who pushes and opens the PR; review step). Reinterprets: D-001, D-002, D-004, D-006 and D-007

## Context
The workflow in `memory/` (ADR-0006, `ACCESS.md`, `TASKS.md`, `STATE.md`) was run by a single agent session with a coordinator and three subagents (builder, reviewer, governance). That session has ended. The lab now runs on Firstmate, an orchestrator that dispatches isolated worker agents ("crewmates"), each on its own git worktree and branch.

## Decision
Role mapping:

| Before (ADR-0006, D-001) | Now |
|---|---|
| Coordinator | First mate (the orchestrator; talks to the user) |
| Builder | Ship crewmate (writes code and `memory/` on its own branch) |
| Reviewer | Architecture Scout crewmate, read-only, reviews against `memory/architecture.md` |
| Governance | Governance Scout crewmate, read-only |

Changes to ADR-0006:
1. The Ship crewmate may push its own `feature/<id>-<topic>` branch and open the PR for it. It never pushes to `main` and never merges.
2. Every Ship PR is reviewed by an architecture Scout and a governance Scout before it reaches the user. The two Scouts may run in parallel. Serious findings go back to a Ship crewmate on the same branch.
3. **Merge stays human-only, on GitHub.**

Rules that every first mate brief carries:
- `memory/TASKS.md` is the official backlog, continuing the existing numbering. The first mate keeps only a mirror outside the repository.
- Everything in the repository (code, docs, `memory/`, commit messages, PR titles and bodies) is in English.
- No tool attribution anywhere: no `Co-Authored-By` trailer, no "Generated with" line, in commits, PRs or files. Worker agents have commit and PR attribution disabled in their local configuration. Both Scouts check this on every review.
- One writing worker per set of files at a time (`ACCESS.md`). Scouts can run together.
- Snowflake work, credentials, cloud resource creation and credit spend require the user's explicit approval. This ADR states the rule; `ACCESS.md` applies it.

How the earlier decisions read now:
- D-001: the coordinator is now the first mate; builder, reviewer and governance are now the Ship crewmate and the two Scouts.
- D-002 ("only the coordinator writes `memory/`"): `memory/` changes are made by a Ship crewmate, under the first mate's instructions, in a PR the user merges. Scouts never write `memory/`.
- D-004 (a PR only after explicit authorization): the user's approval of a task's scope authorizes the Ship crewmate to open that task's PR. Merge stays human-only.
- D-006: the agent runtime is now Firstmate; agent configuration stays local and unversioned.
- D-007 (mentoring mode): now carried by the first mate.

The day-to-day flow is in `memory/agent-workflow.md`.

## Rejected alternatives
- Keep the coordinator as the only one who pushes: the first mate does not work inside the repository checkout, so every push would need an extra hand-off with no added control; merge is the control point.
- Keep a backlog only in Firstmate: the repository would stop being the record of the work.

## Consequences
The limits on every crewmate are instructions in its brief, not technical blocks: the Ship crewmate's (no merge, no `main`, no credentials) and the Scouts' read-only rule (no commit, push, PR comment or GitHub review), since a Scout also runs in a writable worktree with an authenticated GitHub CLI. There is no branch protection yet (ADR-0017, C2). The governance Scout checks these limits on every PR.
