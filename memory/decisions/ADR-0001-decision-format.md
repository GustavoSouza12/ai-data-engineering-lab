# ADR-0001 — Format and location of decisions

- Date: 2026-11-19
- Status: accepted (decision delegated by the user to the coordinator)

## Context
`memory/architecture.md` says to read the decisions in `decisions/`. The repository already had `memory/DECISIONS.md` with D-001 to D-007.

## Decision
New architecture decisions become ADRs in `memory/decisions/ADR-NNNN-<topic>.md`. `memory/DECISIONS.md` is kept as the history of D-001 to D-007 and also serves as the ADR index.

## Rejected alternatives
- Migrate D-001 to D-007 into ADRs: rewrites history with no gain.
- Keep everything in one file: grows without limit and is hard to review in a PR.

## Consequences
Each ADR can be reviewed and approved in its own PR. The coordinator keeps the index up to date.
