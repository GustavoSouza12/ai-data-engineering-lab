# Access

## Allowed data

Synthetic data only, with no correspondence to real people.

## Never store

- Passwords, tokens, API keys and `.env` contents
- Personal data: real name, email, ID document, phone or address

This data never enters `memory/`, code, tests or commit messages.

## Roles

| Role | Can read | Can write |
| --- | --- | --- |
| Coordinator (main conversation) | Repository and `memory/` | `memory/`. The local agent configuration (not versioned) and `.gitignore` only with the user's explicit approval. Creates branches, pushes and opens PRs per ADR-0006. Does not implement the pipeline. Does not merge. |
| Builder | Approved scope | Code and tests for that scope, committing only on the feature branch it was given. Does not push, merge, open PRs or create remotes. Does not write to `memory/`, the agent configuration or `.env` (an instruction-level restriction, checked by governance). |
| Reviewer | Code, tests and `memory/` | Nothing. Enforced by a read-only tool list (read, search, list). |
| Governance | Code, tests and `memory/` | Nothing. Enforced by a read-only tool list (read, search, list). |

## Concurrency

One writer at a time for the same files. Reviewer and governance can run together. The builder never runs in parallel with another agent that changes files.

## Git and publishing

Remote `origin`: private GitHub repository. PR flow defined in ADR-0006 (accepted): private repository, PR opened by the coordinator with the user's authorization, merge only by the user on GitHub. Everything published is in English and carries no tool attribution.

## Access matrices

This file covers the **agents**. The Snowflake **data roles** matrix (`memory/governance/access_matrix.md`, architecture section 7) will be created in phase 1.
