# ADR-0018 — Synthetic PII as obvious placeholders

- Date: 2026-11-21
- Status: accepted (decided by the user on 2026-11-21)
- Amends: ADR-0002 ("no PII" in the synthetic data)

## Context
ADR-0002 keeps phase 0 free of PII. The MVP (ADR-0017) adds the `investors` source, whose columns are PII in the target architecture (name, email). Governance features (tags, masking by `pii_level`, "no PII in a mart") cannot be exercised without columns that are treated as PII.

## Decision
`investors` uses obviously fake placeholder values, for example `NAME-0001` and `investor-0001@example.invalid` (the `.invalid` top-level domain is reserved and never resolves). No realistic personal data: no plausible names, real domains, tax IDs, phone numbers or addresses.

These columns are still treated as PII for tagging, masking and review: they carry a `pii_level` and follow the same rules as real PII would.

Where placeholder values may appear:
- Allowed: the synthetic generator, the versioned synthetic samples under `data/`, test fixtures, and the format examples in this ADR.
- Never: logs, error and quarantine messages (`reject_reason` names the rule, not the value), `memory/` (beyond these examples), commit messages and PR text. Tests assert on IDs or masks, not on printed values.

## Rejected alternatives
- Realistic fake data (for example from a faker library): could match a real person and would be hard to tell apart from a leak.
- No PII-shaped columns: governance could not be tested.

## Consequences
The rule "never store personal data" in `ACCESS.md` still holds: placeholders are not personal data, but they are handled as if they were. A value that looks like real personal data is a governance finding.
