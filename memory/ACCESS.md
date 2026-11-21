# Access

## Allowed data

Synthetic data only, with no correspondence to real people. PII-shaped columns use obvious placeholders (ADR-0018).

## Never store

- Passwords, tokens, API keys and `.env` contents
- Personal data: real name, email, ID document, phone or address

This data never enters `memory/`, code, tests or commit messages.

## Roles

Runtime and role mapping: ADR-0016. Flow: `memory/agent-workflow.md`.

| Role | Can read | Can write |
| --- | --- | --- |
| User | Everything | Approves scope and open calls; approves Snowflake, credential and credit use; the only one who merges, on GitHub |
| First mate (orchestrator) | Repository, `memory/` and PRs | Nothing in the repository directly. Writes worker briefs and keeps a mirror of `memory/TASKS.md` outside the repository |
| Ship crewmate | Repository and `memory/` | Only its own worktree and `feature/<id>-<topic>` branch: code, tests and, when the brief says so, `memory/`. May push that branch and open a PR. Never merges, never pushes to or commits on `main`, never edits `.env` or the local agent configuration |
| Architecture Scout | Repository, `memory/` and the PR | Nothing. Read-only |
| Governance Scout | Repository, `memory/` and the PR | Nothing. Read-only |

No agent reads, prints or stores credentials. Agents work against dev targets only (local DuckDB; Snowflake only with the user's approval) and never against production resources.

## Concurrency

One writing worker at a time for the same set of files. The architecture and governance Scouts can run together.

## Git and publishing

Remote `origin`: private GitHub repository. PR flow in ADR-0006 as amended by ADR-0016: the Ship crewmate pushes its branch and opens the PR, both Scouts review it, merge only by the user on GitHub. Everything published is in English and carries no tool attribution (no `Co-Authored-By`, no "Generated with"); both Scouts check this on every PR.

## Access matrices

This file covers the **agents**. The Snowflake **data roles** matrix (`memory/governance/access_matrix.md`, architecture section 7) will be created in phase 1.
