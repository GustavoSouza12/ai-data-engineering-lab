# Decisions

History of D-001 to D-007. New architecture decisions live in `memory/decisions/` (ADR-0001).

## ADR index

| ADR | Topic | Status |
| --- | --- | --- |
| [ADR-0001](decisions/ADR-0001-decision-format.md) | Format and location of decisions | accepted |
| [ADR-0002](decisions/ADR-0002-orders-contract-phase0.md) | Phase 0 `orders` dataset and contract | accepted, amended by ADR-0009 and ADR-0018 |
| [ADR-0003](decisions/ADR-0003-duplicate-ids.md) | Reject every occurrence of a duplicate ID | superseded by ADR-0009 |
| [ADR-0004](decisions/ADR-0004-local-stack.md) | Python 3.11 + uv + pytest + dbt-duckdb | accepted |
| [ADR-0005](decisions/ADR-0005-structure-and-data-in-git.md) | Folder structure and data in git | accepted |
| [ADR-0006](decisions/ADR-0006-git-github-agent-flow.md) | Git/GitHub flow with agents | accepted, amended by ADR-0016 |
| [ADR-0007](decisions/ADR-0007-lab-confidentiality.md) | Lab confidentiality | accepted |
| [ADR-0008](decisions/ADR-0008-walking-skeleton.md) | Walking skeleton: Snowflake and dbt already in phase 0 | accepted, sequence changed by ADR-0017 |
| [ADR-0009](decisions/ADR-0009-orders-versioning.md) | `orders` versioning: exact duplicate, version and conflict | accepted, amended on 2026-11-23 (cross-file conflicts) |
| [ADR-0010](decisions/ADR-0010-incremental-pipeline.md) | Incremental, late data, deletes and safe reruns | accepted (design) |
| [ADR-0011](decisions/ADR-0011-quarantine-flow.md) | Quarantine, data quality issues and notification | accepted (design) |
| [ADR-0012](decisions/ADR-0012-serving-customer-app.md) | Serving data to a customer-facing application | accepted (principle) |
| [ADR-0013](decisions/ADR-0013-currencies.md) | Amounts in several currencies: `amount_usd` | accepted |
| [ADR-0014](decisions/ADR-0014-orders-json.md) | Orders JSON and schema changes | accepted (design) |
| [ADR-0015](decisions/ADR-0015-state-and-events.md) | State (`orders`) × events (`order_events`) | accepted |
| [ADR-0016](decisions/ADR-0016-firstmate-agent-runtime.md) | Firstmate as agent runtime | accepted |
| [ADR-0017](decisions/ADR-0017-vertical-slice-mvp.md) | Vertical-slice MVP (C1–C5, T1–T12) | accepted; critical path approved |
| [ADR-0018](decisions/ADR-0018-synthetic-pii-placeholders.md) | Synthetic PII as obvious placeholders | accepted |

Runbooks in `memory/runbooks/` (RB-001: a metric jumped).

## D-001 — The coordinator is the main conversation

- Date: 2026-11-19
- Owner: user, recorded by the coordinator
- Status: accepted
- Decision: the coordinator is the parent agent for this folder. Builder, reviewer and governance are subagents.
- Reason: approval before implementation has to stay in the conversation with the user.
- Note (2026-11-19): the subagent definitions are local agent-runtime configuration and are not versioned (D-006, T-027).

## D-002 — Memory has a single writer

- Date: 2026-11-19
- Owner: user, recorded by the coordinator
- Status: accepted
- Decision: only the coordinator updates `memory/`. Specialists return reports.
- Reason: avoid concurrent changes to the same files.

## D-003 — Tests have three states

- Date: 2026-11-19
- Owner: user, recorded by the coordinator
- Status: accepted
- Decision: `proposed`, `executed` and `approved` are distinct states. Only the user's explicit acceptance makes a test `approved`.
- Reason: a successful run is not acceptance.

## D-004 — Pull requests require a remote and authorization

- Date: 2026-11-19
- Owner: user, recorded by the coordinator
- Status: accepted
- Decision: no remote, no pull request. With a remote, a pull request is only prepared after explicit authorization. Merging is not authorized.
- Reason: this repository was local and the user had not authorized publishing or merging.
- Note (2026-11-19): ADR-0006 defines the PR flow once a remote exists. Merge stays human-only.

## D-005 — Synthetic data and no secrets in memory

- Date: 2026-11-19
- Owner: user, recorded by the coordinator
- Status: accepted
- Decision: the work uses synthetic data only. `memory/` stores no credentials and no personal data.
- Reason: governance constraint set by the user.

## D-006 — Agent runtime migration

- Date: 2026-11-19
- Owner: user (approval), recorded by the coordinator
- Status: accepted
- Decision: the workflow moved to a new agent runtime. The coordinator's rules and the subagent definitions (builder, reviewer, governance) are local configuration. Reviewer and governance are read-only through their tool list (read, search, list only). Flow: User → Coordinator → Builder / Reviewer / Governance → `memory/` → PR (only with a remote and authorization, D-004).
- Reason: the previous runtime's configuration was not loaded by the new one, and delegation had never been confirmed (T-002).
- Known limit: the ban on the builder editing `memory/` and the agent configuration is an instruction only; governance checks it afterwards.
- Note (2026-11-19, T-027): the agent configuration is kept out of the repository; only `memory/` documents the workflow.

## D-007 — Mentoring mode

- Date: 2026-11-19
- Owner: user, recorded by the coordinator
- Status: accepted
- Decision: the coordinator explains the why of each step and names the AI Engineering and AI Data Engineering concepts involved, with one optional exercise per step.
- Reason: the lab also serves to train the user as an AI Data Engineer.

## Note on D-001, D-002, D-004, D-006 and D-007 (2026-11-21)

The runtime changed to Firstmate (ADR-0016). The coordinator is now the first mate; builder, reviewer and governance are now the Ship crewmate and the architecture and governance Scouts. D-002 now reads: `memory/` is changed by a Ship crewmate under the first mate's instructions, in a PR the user merges. D-004 now reads: the user's approval of a task's scope authorizes the Ship crewmate to open that task's PR; merge stays human-only. D-007's mentoring mode is now carried by the first mate.
