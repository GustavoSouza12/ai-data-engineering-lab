# Data platform architecture v0: SUBSCRIBE lab

> **Status:** v0, to be validated. This is a **lab with synthetic data** that reproduces SUBSCRIBE's data scope. Nothing here uses the company's real code, schemas or data.
> **Use:** architecture memory for the coordinator and the agents. Before any task, read this file, `STATE.md` and the decisions in `decisions/`.

---

## 1. Goal

Build a data platform that:
1. **Delivers reliable data to customers and partners** (North Star: go from ~10 of ~300 customers receiving data to a repeatable process).
2. **Protects sensitive data** (investor PII, per-fund entitlements, auditing).
3. **Serves the business cases:** order lifecycle and NIGO, freemium → paid, fund data quality, partners (FactSet, Alter Domus) and an AI-ready layer (MCP).

## 2. Principles
- **One source of truth:** golds in Snowflake. Marts and feeds do not create new metric logic.
- **Nothing published without tests:** write-audit-publish on every layer someone consumes.
- **Governance by default:** every column has a `pii_level`; no mart exposes PII; access through functional roles.
- **Everything as code and through PRs:** models, DAGs, roles, grants, policies and shares.
- **Idempotency:** any run can be repeated for any date without duplicating.
- **Agents build and review; the platform runs on its own.** No agent writes to production.

## 3. Overview

### 3.1 Summary view

```mermaid
flowchart LR
  subgraph Sources
    A[Product: orders, events, investors, funds, sponsors, billing]
    B[Fund document extraction JSON]
    C[Market reference CSV, Preqin-like]
    D[Usage events]
  end
  subgraph Snowflake
    RAW[RAW / bronze]
    STG[STAGING / silver]
    INT[INTERMEDIATE]
    GS[GOLD_STAGING]
    G[GOLD]
    M[MARTS]
    SH[SHARES: secure views]
  end
  A & B & C & D --> RAW --> STG --> INT --> GS
  GS -- audit ok: SWAP --> G --> M
  M --> SH
  M --> BI[Metabase]
  M --> P[Portal views: contract with backend]
  SH --> FX[FactSet]
  SH --> AD[Alter Domus]
  M --> MCP[Semantic layer + MCP]
  AF[Airflow] -. orchestrates .-> RAW & GS & G & SH
```

### 3.2 Full data flow: from source to customer

> Elements marked **(proposed)** come from the quarantine flow discussion (T-019) and are designed in ADR-0011: `ORDERS_QUARANTINE` in `RAW`, `ANALYTICS.DQ_FAILURES`, `OPS.DATA_QUALITY.DQ_ISSUES` and `DQ_OWNERS`.

```mermaid
flowchart LR
  subgraph SRC["1. Sources"]
    S1["orders, order_events"]
    S2["investors - PII"]
    S3["funds, sponsors, billing"]
    S4["fund_documents_extracted - AI JSON"]
    S5["market_reference - licensed CSV"]
    S6["usage_events"]
  end

  subgraph ING["2. Ingestion - Python loader, LOADER role"]
    V{"Structural validation<br/>header, required fields,<br/>conflicting versions, extra fields"}
  end

  subgraph RAWDB["3. RAW - bronze"]
    R1["One table per source<br/>+ _source_file, _loaded_at"]
    RQ["*_QUARANTINE (proposed)<br/>raw row + reject_reason<br/>same PII tags as the source"]
  end

  subgraph ANDB["4. ANALYTICS - TRANSFORMER role"]
    STG["STAGING - silver<br/>cast, rename, exact dedup"]
    INT["INTERMEDIATE<br/>business rules"]
    GS["GOLD_STAGING<br/>WRITE: zero-copy clone of GOLD + build"]
    AUDIT{"AUDIT<br/>dbt tests + reconciliation<br/>within limits?"}
    G["GOLD - source of truth<br/>fct_orders, dim_fund, dim_investor"]
    M["MARTS<br/>internal, portal, partners, ai"]
    SH["SHARES<br/>secure views, only the needed columns"]
    DQF["DQ_FAILURES (proposed)<br/>store_failures from tests"]
  end

  subgraph GOVDB["5. GOVERNANCE"]
    TAGS["TAGS + POLICIES<br/>masking by pii_level"]
    ENT["ENTITLEMENTS<br/>fund_entitlements"]
    OWN["DQ_OWNERS (proposed)<br/>rule or source to owning team"]
  end

  subgraph OPSDB["6. OPS"]
    RUNS["PIPELINE_RUNS<br/>runs, SLOs"]
    DQI["DATA_QUALITY.DQ_ISSUES (proposed)<br/>open, acknowledged, resolved,<br/>wont_fix, escalated"]
    AUD["AUDIT<br/>weekly governance report"]
  end

  subgraph NOTIF["7. Notification"]
    SLACK["Slack data-alerts<br/>pipeline failures + runbook"]
    MAIL["Email to the source owner<br/>count, rule, IDs and link<br/>NEVER the row with PII"]
    PANEL["Data quality dashboard in Metabase"]
  end

  subgraph OUT["8. Consumers"]
    BI["Internal team<br/>Metabase, BI_READER role"]
    PORTAL["Investor portal<br/>views with a versioned contract"]
    FX["FactSet<br/>secure data share"]
    ADX["Alter Domus<br/>secure data share"]
    FILE["Customers without Snowflake<br/>reader account or S3 + manifest"]
    MCP["AI: semantic layer + MCP<br/>per-customer isolation"]
  end

  AF(["Airflow + Cosmos<br/>orchestrates everything"])

  S1 --> V
  S2 --> V
  S3 --> V
  S4 --> V
  S5 --> V
  S6 --> V
  V -->|structure ok| R1
  V -->|rejected| RQ

  R1 --> STG --> INT --> GS --> AUDIT
  STG -.->|test failed| DQF
  GS -.->|test failed| DQF
  AUDIT -->|yes: PUBLISH via SWAP| G
  AUDIT -->|no: nothing published| SLACK
  G --> M --> SH

  RQ --> DQI
  DQF --> DQI
  OWN -.->|who owns it| MAIL
  DQI -->|new or escalated issue| MAIL
  DQI --> PANEL

  TAGS -.->|masks| RQ
  TAGS -.->|masks| G
  TAGS -.->|masks| M
  ENT -.->|row access| M
  ENT -.->|row access| SH

  M --> BI
  M --> PORTAL
  M --> MCP
  SH --> FX
  SH --> ADX
  SH --> FILE

  AF -.-> V
  AF -.-> STG
  AF -.-> AUDIT
  AF -.-> SH
  AF --> RUNS
  RUNS --> AUD
```

**One order going through the flow (example `ORD-00117`, same version key with different content):**

| Step | Where | What happens |
|---|---|---|
| 1 | `orders` source | The order system sends two rows with the same `order_id` and the same `updated_at`, but different investors and amounts (a conflict, ADR-0009; versions with different `updated_at` would be legitimate) |
| 2 | Ingestion | Structural validation detects the conflict; both rows go to `RAW.ORDERS.ORDERS_QUARANTINE` with `reject_reason = conflicting_version` |
| 3 | RAW | The other orders in the file flow normally; the quarantine inherits the source's PII tags |
| 4 | DQ_ISSUES | The `MERGE` opens an issue with `issue_key = hash(rule, order_id)`; if the collision persists tomorrow, it only updates `last_seen` |
| 5 | Notification | The owner in `DQ_OWNERS` (the order system team) gets an email with the count, rule, ID and dashboard link, with no personal data |
| 6 | Fix | The owner fixes it at the source; the next load brings one row per version key |
| 7 | Resolution | The `MERGE` no longer finds the failure and marks the issue `resolved`, with `resolved_at` |
| 8 | Gold and customers | The order enters `fct_orders` and reaches the marts, the portal and the shares only after passing the audit |

### 3.3 Daily run and notification triggers

```mermaid
flowchart TD
  T0(["03:00 ET - daily_platform DAG"]) --> L["LOAD<br/>Python loader into RAW<br/>staging + quarantine"]
  L --> LQ{"Ingestion quarantine<br/>above the limit?"}
  LQ -->|yes| STOP1["STOP the DAG<br/>Slack CRITICAL: broken file or source"]
  LQ -->|no| FR{"Freshness:<br/>did every source arrive?"}
  FR -->|no| STOP2["STOP the DAG<br/>Slack CRITICAL: late source"]
  FR -->|yes| B["WRITE<br/>dbt build into GOLD_STAGING<br/>store_failures into DQ_FAILURES"]
  B --> DQ["MERGE into DQ_ISSUES<br/>always runs, even if the audit fails"]
  B --> TST{"dbt tests"}
  TST -->|error_if exceeded| STOP3["NOTHING PUBLISHED<br/>Slack CRITICAL + runbook"]
  TST -->|warn_if only| REC
  TST -->|all ok| REC{"Reconciliation<br/>count and sum<br/>source x gold"}
  REC -->|difference| STOP3
  REC -->|zero| P["PUBLISH<br/>SWAP GOLD with GOLD_STAGING"]
  P --> SHV["Refresh SHARES views"]
  SHV --> OK["Slack INFO: published + metrics<br/>volume, quarantined rows"]
  DQ --> N1["Email to the owner<br/>new issues"]
  DQ --> N2["Email to the owner's manager<br/>issues open for more than 7 days"]

  W(["07:00 and 08:00 ET - sla_watchdog DAG"]) --> WQ{"Did today's publish<br/>happen?"}
  WQ -->|no, 07:00| WN["Slack WARNING"]
  WQ -->|no, 08:00| WC["Slack CRITICAL + on-call"]
  WQ -->|yes| VOL{"Volume within<br/>30% of the 7-day average?"}
  VOL -->|no| WV["Slack WARNING: volume anomaly"]

  GW(["Monday 06:00 ET - governance_weekly DAG"]) --> GR["Report in OPS.AUDIT<br/>grants outside the matrix, new roles,<br/>access to restricted columns, PII in marts"]
  GR --> GN["Email to governance<br/>PII in a mart = CRITICAL"]

  classDef stop fill:#ef4444,stroke:#7f1d1d,stroke-width:3px,color:#ffffff
  classDef warn fill:#facc15,stroke:#854d0e,stroke-width:3px,color:#1a1a1a
  classDef go fill:#22c55e,stroke:#14532d,stroke-width:3px,color:#1a1a1a
  class STOP1,STOP2,STOP3,WC stop
  class N1,N2,WN,WV,GN warn
  class P,SHV,OK go
```

Color legend: **red** = conservative posture, the pipeline stops and nothing is published · **yellow** = permissive posture with a warning, publish and notify · **green** = normal path. Details for each point in section 3.5.

| Trigger | When it fires | Severity | Channel | Who receives it | Gold published? |
|---|---|---|---|---|---|
| Invalid header or loader crash | At load | Critical | Slack + runbook | Data team | No |
| Ingestion quarantine above the limit | At load | Critical | Slack | Data team | No |
| Source did not arrive (freshness) | Before the build | Critical | Slack | Data team + source owner | No |
| dbt test above `error_if` | At audit | Critical | Slack + runbook | Data team | No |
| dbt test above `warn_if` | At audit | Warning | Email | Rule owner (`DQ_OWNERS`) | Yes |
| Reconciliation not zero | At audit | Critical | Slack | Data team | No |
| New issue in `DQ_ISSUES` | After the build | Warning | Email without PII + dashboard | Source owner | Yes |
| Issue open for more than 7 days | After the build | Escalation | Email | Owner's manager | Yes |
| No publish by 07:00 / 08:00 | `sla_watchdog` | Warning / critical | Slack / on-call | Data team | — |
| Volume outside 30% of the average | `sla_watchdog` | Warning | Slack | Data team | Already published |
| PII found in a mart | `governance_weekly` | Critical | Email | Governance | Already published: fix with priority |

### 3.4 Backfill: reprocess a range without duplicating

```mermaid
sequenceDiagram
  actor ENG as Engineer
  participant AF as Airflow, backfill DAG
  participant LD as Python loader
  participant RAW as RAW
  participant DBT as dbt
  participant GS as GOLD_STAGING
  participant G as GOLD
  participant DQ as DQ_ISSUES

  ENG->>AF: triggers backfill from 2026-11-01 to 2026-11-30, with approval
  AF->>GS: zero-copy clone of the current GOLD
  loop for each logical_date in the range
    AF->>LD: run-ts = logical_date, never the clock
    LD->>RAW: replaces only that day's partition, key _source_file
    AF->>DBT: dbt build with run_date = logical_date
    DBT->>GS: incremental with unique_key and a 3-day lookback
  end
  AF->>AF: AUDIT of the whole range, tests + reconciliation
  alt audit ok
    AF->>G: PUBLISH with a single SWAP
    AF->>DQ: MERGE, fixed issues become resolved
    AF-->>ENG: Slack INFO with the backfill summary
  else audit failed
    AF-->>ENG: Slack CRITICAL, GOLD untouched, nothing published
  end
```

**Why the backfill does not duplicate:** time comes from the `logical_date` (never `now()`), RAW replaces the day's partition instead of appending, incrementals use `unique_key`, and gold only changes through a `SWAP` after the audit. Rollback is another `SWAP`.

### 3.5 Posture per control point: conservative × permissive

Every control point chooses between two errors: publishing wrong data (permissive) or holding back correct data (conservative). The general rule for this platform: **permissive with the individual record, conservative with the batch and with everything that reaches a customer.** Governance has no permissive mode.

| Control point | Where (3.2 / 3.3) | Posture | Limit or trigger | Why | Decision |
|---|---|---|---|---|---|
| Row with a structural error | Ingestion | Permissive per row | The row goes to quarantine; the rest continues | One bad order should not stop the business | ADR-0002, ADR-0011 |
| Quarantine volume | Ingestion (LQ) | Conservative per batch | Above the limit, the DAG stops | Many rejections = broken file or source | ADR-0011 |
| Version conflict, including an incomplete row with the same key | Ingestion | Conservative | Both occurrences go to quarantine | No rule says which one is true | ADR-0009 (F1) |
| Versions and exact duplicates | Staging / intermediate | Permissive | `row_number` by `updated_at` | There is a business rule: the latest version wins | ADR-0009 |
| Late source | Freshness (FR) | Conservative | `error_after` | Publishing incomplete data looks like correct data | ADR-0010 |
| Semantic test | Audit (TST) | By threshold | `warn_if` publishes and warns; `error_if` stops | Small noise × systemic breakage | ADR-0011 |
| Reconciliation | Audit (REC) | Conservative | Difference ≠ 0 stops | A count or sum difference is lost or invented data | Section 11 |
| Gold publish | Publish | Conservative | Only `SWAP` after the audit | Consumers never see a half-finished build | Section 9 |
| Portal view and application | Marts / portal | Conservative + last known good | On failure, keep the previous version, with its date | Customers never see an empty screen or an unaudited number | ADR-0012 |
| Isolated data quality issue | DQ_ISSUES | Permissive with a warning | Publish and notify the owner | The owner fixes it at the source; the rest of the data flows | ADR-0011 |
| Volume or sum anomaly | `sla_watchdog` | Permissive with a warning | Outside 30% of the average: warning | Could be real business; a human decides | Section 11, RB-001 |
| PII in a mart, access outside the matrix | `governance_weekly` | Conservative, always | Critical and priority fix | Improper access cannot be undone | Section 7 |

## 4. Sources (synthetic in the lab)

| Source | Content | Sensitivity |
|---|---|---|
| `organizations` | Customer organizations (sponsors and advisor firms) | Internal |
| `orders` | Versioned subscription order: organization, investor, fund, amount, currency, channel, status, `updated_at` (ADR-0009) | Internal |
| `order_events` | Order states: submitted, sponsor_review, nigo, approved, signed, completed, cancelled | Internal |
| `orders_json` | Order document as JSON: investor, product, status and NAV history (ADR-0014) | **PII** (investor name) |
| `fx_rates` | Daily exchange rates to USD (synthetic seed in phase 0, ADR-0013) | Public |
| `investors` | Name, email, tax ID, date of birth, KYC | **Restricted/confidential PII** |
| `funds` | Name, type, strategy, sector, fees, minimums, terms | Internal |
| `sponsors` | Fund managers (GPs) | Internal |
| `billing`, `billing_contract`, `billing_contract_fee` | Contracts and fees (basis for freemium) | Confidential |
| `fund_documents_extracted` | AI extraction output (JSON), with per-field confidence | Internal |
| `market_reference` | External fund classification (Preqin-like) | Licensed |
| `usage_events` | Platform usage by sponsor and advisor | Internal |
| `fund_entitlements` | Which advisors/firms can see which funds | Confidential |

**Ingestion:** at SUBSCRIBE, Airbyte. In the lab, a Python loader → stage → `COPY INTO` into `RAW`, with a `_loaded_at` column.

## 5. Snowflake

### Databases and schemas
| Database | Schemas | Use |
|---|---|---|
| `RAW` | one per source | Bronze: data as it arrived |
| `ANALYTICS` | `STAGING`, `INTERMEDIATE`, `GOLD`, `GOLD_STAGING`, `MARTS`, `SHARES` | Silver, gold, WAP, consumption, external exposure |
| `GOVERNANCE` | `TAGS`, `POLICIES`, `ENTITLEMENTS` | PII tags, masking, row access, access maps |
| `OPS` | `PIPELINE_RUNS`, `AUDIT` | Runs, SLOs, governance reports |
| `ANALYTICS_DEV` | `PR_<n>_*` and one per developer | CI and development |

### Functional roles
| Role | Can | Cannot |
|---|---|---|
| `LOADER` | Write to `RAW` | Read gold |
| `TRANSFORMER` | Read `RAW`, write `ANALYTICS`; sees unmasked PII (otherwise it would write masked values into gold) | Be granted to people |
| `ANALYST` | Read `GOLD` and `MARTS`, PII masked | Write |
| `BI_READER` | Read `MARTS` (Metabase) | Read `RAW`/`STAGING` |
| `PORTAL_READER` | Read portal views | Read anything else |
| `PARTNER_FACTSET`, `PARTNER_ALTER_DOMUS` | See only their own share | Anything else |
| `GOVERNANCE_ADMIN` | Create tags, policies, entitlements | Read business data |
| `GOVERNANCE_AUDITOR` | Read metadata (`ACCOUNT_USAGE`: grants, tags, access) | Read data |
| `CI_ROLE` | Write to `ANALYTICS_DEV` | Touch production |

### Warehouses
`LOAD_WH`, `TRANSFORM_WH`, `BI_WH`, `CI_WH`: all XS, `auto_suspend = 60`, with a resource monitor. Reader accounts with their own warehouse and monitor.

## 6. dbt

### Structure
```
models/
  staging/        stg_<source>__<table>   views, cast + rename + known dedup
  intermediate/   int_order_events_sequenced, int_fund_classification_mapped
  gold/
    orders/       fct_orders, fct_order_events, fct_sponsor_reviews (NIGO)
    funds/        dim_fund (official taxonomy), fct_fund_completeness
    parties/      dim_investor (PII with tags), dim_sponsor (paid/free), dim_advisor
    usage/        fct_sponsor_activity
  marts/
    internal/     mart_cs_client_health, mart_sponsor_growth (freemium), mart_product_onboarding
    portal/       mart_portal_investor_positions_v1 (contract with backend)
    partners/     mart_partner_factset_v1, mart_partner_alter_domus_v1
    ai/           mart_mcp_orders, mart_mcp_funds
seeds/            fund_taxonomy, fund_classification_map
snapshots/        snap_funds (terms, fees, strategy), snap_investor_kyc
tests/            singular: order lifecycle, reconciliation, no PII in marts
macros/           governance (tags, row access), publish_gold (SWAP), generate_schema_name
```

### Rules (the reviewer checks)
- Every gold: PK with `unique` + `not_null`, description, `meta.owner`.
- Every column: `meta.pii_level` (`restricted`, `confidential`, `internal`, `public`).
- Input tests on staging, so dbt skips gold when the input is wrong.
- Partner and portal marts: `contract: enforced`, `versions`, `exposures`, `grants`.
- `store_failures` on critical tests.
- Source × gold reconciliation (count and sum of amounts).
- Incrementals with `unique_key` and a 3-day lookback window.

## 7. Governance
- **PII:** `PII_LEVEL` tag + tag-based masking (string, date). A post-hook reapplies tags after `create or replace`.
- **Per-fund entitlements:** `GOVERNANCE.ENTITLEMENTS.FUND_ENTITLEMENTS` + a row access policy on marts that go to the portal and partners.
- **External exposure:** only secure views in the `SHARES` schema; one share per partner, with only the needed columns.
- **Auditing:** weekly report (`OPS.AUDIT`): grants outside the matrix, new roles, access to restricted columns, marts with PII.
- **Access matrix:** `memory/governance/access_matrix.md`, approved by humans.

## 8. Orchestration (Airflow + Cosmos)

| DAG | When | What it does |
|---|---|---|
| `daily_platform` | 03:00 ET | Load → freshness → `dbt build` (gold into `GOLD_STAGING`) → reconciliation → **publish (SWAP)** → refresh share views → notify |
| `sla_watchdog` | 07:00 and 08:00 ET | Warning and critical alert if the publish did not happen |
| `governance_weekly` | Monday 06:00 ET | Produces the audit report |
| `backfill` | Manual | Reprocesses a date range, idempotently |

Retries only for transient errors, with backoff. Timeouts on every task. Failure → Slack alert with a runbook link.

## 9. Write-audit-publish
1. **Write:** `dbt build --vars '{gold_schema: GOLD_STAGING}'`
2. **Audit:** dbt tests + reconciliation. Failed → stop, alert, nothing published.
3. **Publish:** `ALTER SCHEMA ANALYTICS.GOLD SWAP WITH ANALYTICS.GOLD_STAGING`.
4. **Rollback:** another `SWAP` goes back to the previous version.
5. **Watch out:** grants, tags and policies must exist on both schemas.

## 10. CI/CD (GitHub Actions)
- **CI on the PR:** `sqlfluff` + `ruff` + `pytest` + offline `dbt parse` + project rules (manifest) → `dbt build --select state:modified+ --defer` into `PR_<n>_*` → artifacts → cleanup job when the PR closes.
- **CD on `main`:** `production` environment with approval → build with WAP → publishes `manifest.json` (Slim CI state).
- **Infrastructure as code:** roles, warehouses, grants, tags, policies and shares through Terraform or versioned scripts, with `plan` on the PR and an approved `apply`.
- **Protection:** protected `main`, required status checks, CODEOWNERS, PR template.

## 11. Observability and SLOs
| SLO | Target |
|---|---|
| Gold publish | by 07:00 ET on 99% of days |
| Daily volume | within ±30% of the 7-day average |
| PII in marts | zero |
| Reconciliation | zero difference in count and sum |

Signals: freshness, volume, **sum of amounts in USD against the 7-day average** (an amount jump with normal volume only shows up here), grain (`count(*)` = `count(distinct key)` on every gold), schema (contracts), distribution (% nulls), lineage (exposures). Investigating jumps: `memory/runbooks/RB-001-metric-jumped.md`. Runs in `OPS.PIPELINE_RUNS`. Runbooks in `memory/runbooks/`.

## 12. Distribution
| Consumer | Channel | Owner |
|---|---|---|
| Internal team | Metabase on `MARTS` (`BI_READER` role) | Data |
| Investor portal | Views with a contract | Data delivers the view; backend builds the API |
| FactSet, Alter Domus | Secure data sharing (or a listing, if another region/cloud) | Data |
| Customers without Snowflake | Reader account or a file in S3 with a manifest | Data |
| AI | Semantic layer + MCP over `mart_mcp_*`, per-customer isolation | Data + backend |

## 13. Agents (how they build this platform)
| Agent | Touches | Never |
|---|---|---|
| Coordinator | Plans, breaks work into tasks, updates `STATE.md` | Merges |
| Builder | dbt code, DAGs, governance SQL, tests | Writes to production |
| Reviewer | Reads the diff and test results; comments | Changes code |
| Governance | Reads code and metadata (`GOVERNANCE_AUDITOR` role) | Reads data, grants access, changes policies |

Agent conclusions are auxiliary checks, not guarantees. Approval is human.

Runtime and current role names (first mate, Ship crewmate, architecture and governance Scouts): ADR-0016 and `memory/agent-workflow.md`.

## 14. Lab roadmap
| Phase | Delivers |
|---|---|
| 0 | **Walking skeleton (ADR-0008):** F0.1 Python ingestion with versioning (ADR-0009); F0.2 dbt with `organizations`, `orders`, `order_events`, `fx_rates` and `org_summary`; F0.3 Snowflake `RAW` + quarantine + CI; F0.4 orders JSON with NAV and reconciliation (ADR-0014) |
| 1 | Snowflake: roles, warehouses, `RAW` loaded |
| 2 | dbt: staging → gold → marts with tests and docs |
| 3 | Governance: PII, entitlements, auditing |
| 4 | Airflow + WAP + alerts + SLOs |
| 5 | CI/CD with Slim CI and infrastructure as code |
| 6 | Partner shares + file feed |
| 7 | Data products: freemium, fund quality |
| 8 | Semantic layer + MCP |

## 15. Assumptions to confirm at SUBSCRIBE (not verified)
- [ ] Where dbt runs today and whether there is an orchestrator (Airflow does not exist yet, from what I heard)
- [ ] Region and cloud of the FactSet and Alter Domus Snowflake accounts
- [ ] Source of truth for "who pays" (assumption: billing tables)
- [ ] Where per-fund entitlements live today
- [ ] Policy on using AI assistants with company code
- [ ] Whether Terraform or another infrastructure-as-code tool exists

## 16. Out of scope for now
Real-time streaming, data mesh, warehouse migration, data monetization (comes after the foundation).
