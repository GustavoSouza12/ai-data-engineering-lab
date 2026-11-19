# ADR-0012 — Serving data to a customer-facing application

- Date: 2026-11-19
- Status: accepted as a principle; numeric SLAs to be negotiated with the backend team (phase 6)

## Context
When an application shows data directly to customers, an error stops being "a wrong dashboard" and becomes "a customer seeing a wrong number". The pipeline becomes a **product with a contract**, not a report.

## Decision

| Topic | Decision |
|---|---|
| Serving layer | The application reads only `MARTS.portal` (versioned views `_v1`, `_v2`), never gold, staging or RAW. A `PORTAL_READER` role and its own warehouse, so heavy BI does not degrade the application |
| Reliability | WAP is mandatory. If publishing fails, the application keeps reading the last known good version: never an empty or partial screen |
| Freshness | Each view exposes `_published_at`. The application shows "updated at", and the freshness SLO is agreed with the backend team (daily at 07:00 works for BI; customers may need hourly, which changes orchestration) |
| Monitoring | Beyond the signals in section 11: age of `_published_at`, business invariants before publishing (for example, no investor with a negative balance) and consumption checks (API errors) |
| Failures | No manual fixes directly in the view. Fix = PR → CI → publish. Rollback = `SWAP`. A customer-facing incident follows a runbook and communication with the CS team |
| Schema changes | `contract: enforced` in dbt. An **additive** change (new column) can go into the current version. A **breaking** change (remove, rename, change type or meaning) requires a new version |
| Compatibility | `_v1` and `_v2` coexist for at least 90 days. Deprecation is announced to the backend team through dbt `exposures` and CODEOWNERS on the PR |
| Correctness | Consumer-side contract tests run in CI. Monetary values come with their currency; never sum different currencies |

## Consequences
The data team takes on on-call duty and a formal SLO. Every portal view needs an owner, a version and a contract test before going to production.
