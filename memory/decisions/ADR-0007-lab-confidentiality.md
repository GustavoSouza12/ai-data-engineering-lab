# ADR-0007 — Lab confidentiality

- Date: 2026-11-19
- Status: accepted (decision delegated by the user to the coordinator)

## Context
`memory/architecture.md` reproduces the data scope of a real company and mentions real partners. The company's policy on AI assistants has not been verified (section 15).

## Decision
- No code, schema, internal table name or real data from the company enters the repository. All data is synthetic.
- Company names appear only as context in the architecture, never in test data.
- The remote repository is private.
- Governance checks this on every review.

## Consequences
If the company's policy restricts this use, the lab must be reviewed before anything is published.
