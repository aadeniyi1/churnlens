# Product Requirements Document: ChurnLens

| | |
|---|---|
| **Product** | ChurnLens: churn intelligence for B2B SaaS |
| **Author** | Ade (github.com/aadeniyi1) |
| **Status** | v1 shipped (modules A, B, C, D, F). Modules E and G are roadmap |
| **Related** | [BRD](brd.md) · [Workflow maps](workflows.md) · [Metrics](metrics.md) · [Model card](model_card.md) · [API guide](api_integration.md) |

> All figures come from ChurnLens's synthetic dataset (3,000 accounts, seed 42). They show how the
> product would be measured, not results from a real company.

---

## 1. Problem

A B2B SaaS company with about $42M ARR is growing, but it is leaking revenue. 12-month **net revenue
retention is 93%** and **gross revenue retention is 84%**. SMB is worst, at 72% GRR.

Customer success (CS) learns an account is at risk too late, usually when the customer gives notice
at renewal. By then there is nothing left to save. The warning signs show up 6 months earlier, but
they live in four different systems:

| Signal | Where it lives today | Who can see it |
|---|---|---|
| Contract value, renewal dates, seat changes | Billing / CRM | Finance, RevOps |
| Product usage and seat utilization | Product telemetry | Product, data team |
| Tickets, SLA breaches, CSAT | Help desk | Support |
| Parent/child company structure, segment | CRM | Sales |

No one sees all four together, so a CSM managing 70 accounts can't tell which 5 need attention
this week.

**Evidence from the data** (see [the analysis notebook](../analysis/retention_story.ipynb)):

- Churning customers use **40% of their seats** in the 6 months before renewal, against 70% for customers who renew.
- Customers below **40% seat use in their first 90 days** churn at first renewal **34%** of the time, against 15% above 70%.
- Churners file about 40% more tickets and give lower CSAT (3.1 vs 3.7).

## 2. Goals and non-goals

**Goals**

1. Flag at-risk accounts **at least 90 days before renewal**, early enough for CS to act.
2. Explain **why** each account is flagged in plain language, so a CSM knows what to do first.
3. Give leadership one trusted set of retention numbers (ARR, NRR, GRR, cohorts).
4. Make the scores available to other tools (CRM, Slack) through an API, so people don't have to log in somewhere new.

**Non-goals for v1**

- Automatically taking action on accounts (emails, discounts). People decide; ChurnLens informs.
- Real-time scoring. Monthly scores match annual contracts and monthly CS reviews.
- Predicting expansion or upsell. Possible later; the data supports it.

## 3. Users

| Persona | Job to be done | Main surface |
|---|---|---|
| **Maya, VP Customer Success** | "Tell me where my team should spend time this week, and whether retention is improving." | Dashboard: Home, Risk List |
| **Sam, Customer Success Manager** (70 accounts) | "Before a call, show me what changed with this account and what to talk about." | Dashboard: Account 360; CRM field via API |
| **Priya, RevOps / Finance** | "Give me NRR and GRR I can put in the board deck, with clear definitions." | Dashboard: Home, Cohorts; API metrics |
| **Leo, Support lead** | "Show me where SLA misses are hurting renewals." | Dashboard: Support and SLA |
| **Dana, Data team** | "Keep the pipeline correct and show that the model can be trusted." | Data quality checks, Model page, CI |
| **Integration engineer** (customer or internal) | "Pull scores into our CRM every night." | REST API, `examples/client.py` |

## 4. Success metrics

| Metric | Baseline (synthetic) | v1 target | How measured |
|---|---|---|---|
| GRR, 12-month | 84% | +3 pts within 4 renewal quarters | `metric_retention_12m` |
| Share of churned ARR flagged High/Medium 90+ days before renewal | n/a | ≥ 60% | Back-test on renewals |
| Precision of the riskiest 10% | n/a | ≥ 70% | Model test set: **80%** today |
| Churned ARR captured in the riskiest 10% | n/a | ≥ 40% | Model test set: **50%** today |
| CSMs opening Risk List or Account 360 weekly | 0 | 80% of CSMs | Usage analytics (future) |
| High-risk accounts with a logged action within 14 days | n/a | 90% | Needs module G (playbooks) |

Guardrail: the data quality suite (18 checks) must pass before any score is published.

## 5. Scope

| Module | What it covers | v1 status |
|---|---|---|
| **A. Contracts and revenue** | Contracts, renewals, ARR by month, ARR bridge (new, expansion, contraction, churn), NRR, GRR, cohorts | ✅ Shipped |
| **B. Usage and license utilization** | Product events, monthly active users, seat utilization, key-feature share, usage trend | ✅ Shipped |
| **C. Support and SLA** | Tickets, priority, first-response time, SLA breach, CSAT | ✅ Shipped |
| **D. Account hierarchy and segments** | Parent/child/ultimate parent, segment, region, industry, CSM ownership | ✅ Shipped |
| **E. Partner channel** | Partner-sourced and partner-managed accounts, partner performance | 🗺️ Roadmap (§9) |
| **F. Health score and churn model** | Rule-based health score with reasons, ML churn probability, ARR at risk | ✅ Shipped |
| **G. CS playbooks** | Recommended action per risk reason, task tracking, outcome logging | 🗺️ Roadmap (§9) |

## 6. Requirements

Priority: **P0** = must have for v1, **P1** = should have, **P2** = nice to have.

### Module A: contracts and revenue

| ID | Requirement | Priority | Status |
|---|---|---|---|
| A1 | Track every contract with start, end, seats, ARR, and renewal outcome (renewed, expanded, contracted, churned, open) | P0 | ✅ |
| A2 | Monthly ARR per account, with an explicit churn month where ARR drops to 0 | P0 | ✅ |
| A3 | ARR bridge per month: new, expansion, contraction, churn | P0 | ✅ |
| A4 | 12-month NRR and GRR, total and by segment, with written definitions | P0 | ✅ |
| A5 | Cohort retention by signup quarter, by ARR and by logos | P1 | ✅ |

### Module B: usage

| ID | Requirement | Priority | Status |
|---|---|---|---|
| B1 | Ingest product events, removing duplicate events | P0 | ✅ |
| B2 | Seat utilization = monthly active users ÷ licensed seats | P0 | ✅ |
| B3 | 3-month usage trend (change against the previous 3 months) | P0 | ✅ |
| B4 | Share of activity in "sticky" features (dashboards, integrations) | P1 | ✅ |
| B5 | First-90-day utilization, to catch slow onboarding | P1 | ✅ |

### Module C: support

| ID | Requirement | Priority | Status |
|---|---|---|---|
| C1 | Ingest tickets, keeping only the latest version of each ticket | P0 | ✅ |
| C2 | SLA breach per ticket against targets P1 = 1h, P2 = 4h, P3 = 24h | P0 | ✅ |
| C3 | CSAT per account, with missing surveys handled explicitly | P0 | ✅ |
| C4 | Ticket volume normalized per 10 seats, so big accounts aren't flagged just for being big | P1 | ✅ |

### Module D: hierarchy and segments

| ID | Requirement | Priority | Status |
|---|---|---|---|
| D1 | Parent, child and ultimate parent for every account | P0 | ✅ |
| D2 | Segment (SMB, Mid-Market, Enterprise), region, industry, CSM | P0 | ✅ |
| D3 | Every report can be filtered by segment and CSM | P0 | ✅ |
| D4 | Roll up risk to the ultimate parent ("is the whole Acme group at risk?") | P2 | Partly: ultimate parent is stored, no roll-up view yet |

### Module F: health score and churn model

| ID | Requirement | Priority | Status |
|---|---|---|---|
| F1 | Health score 0 to 100 from usage trend (35%), utilization (25%), support (25%), contract (15%) | P0 | ✅ |
| F2 | Up to 3 plain-English reasons per account, worst first | P0 | ✅ |
| F3 | Churn probability per account per month, using only data available at that time (no leakage) | P0 | ✅ |
| F4 | Model trained only on snapshots 90+ days before renewal and tested on later renewals | P0 | ✅ |
| F5 | ARR at risk = probability × ARR, used to rank the Risk List | P0 | ✅ |
| F6 | Model card with test results, limits, and feature importance | P1 | ✅ |
| F7 | Score history per account, so CSMs can see a trend | P1 | ✅ |

### Surfaces

| ID | Requirement | Priority | Status |
|---|---|---|---|
| S1 | Web dashboard with Home, Cohorts, Risk List, Account 360, Support, Model pages | P0 | ✅ live |
| S2 | Read-only REST API with key authentication and interactive docs | P0 | ✅ live |
| S3 | Example integration (CRM sync) and integration guide | P1 | ✅ |
| S4 | Slack digest of new high-risk accounts | P2 | Documented pattern, not built |

### Non-functional

| ID | Requirement | Status |
|---|---|---|
| N1 | Full pipeline runs on an 8 GB laptop without Docker | ✅ under 2 minutes, under 1 GB RAM for generation |
| N2 | Runs on macOS and Windows with the same commands | ✅ |
| N3 | Data quality checks block publishing if anything fails | ✅ |
| N4 | Tests and lint run automatically on every change | ✅ GitHub Actions |
| N5 | Data refreshes on a schedule, without manual steps | ✅ nightly workflow |
| N6 | No secrets in code or Git; API protected by key | ✅ |
| N7 | Hosting cost $0 | ✅ Supabase, Streamlit Cloud, Render free plans |

## 7. User experience

The main flow is the **Monday risk review** (see [workflows.md](workflows.md#2-monday-risk-review)):

1. Maya opens **Risk List**, filtered to High and Medium, renewing within 6 months. It's sorted by ARR at risk.
2. She assigns the top accounts to their CSMs in the team meeting.
3. Sam opens **Account 360** for each one: usage trend, tickets, contract history, and the top reasons.
4. Sam picks an action based on the main reason (low utilization → enablement session; SLA misses → escalate to support; contraction last year → exec sponsor call).
5. The next month's scores show whether the account improved.

Step 4 is manual in v1. Module G (CS playbooks) automates it.

## 8. Release plan

| Phase | Delivered |
|---|---|
| 1 | Synthetic source data: accounts, contracts, usage, tickets |
| 2 | DuckDB warehouse (star schema) and 18 data quality checks |
| 3 | Retention analysis notebook: ARR, NRR, GRR, cohorts |
| 4 | Health score, churn model, Streamlit dashboard, Supabase hosting |
| 5 | REST API on Render, example client, integration guide |
| 6 | CI, nightly pipeline, PRD, BRD, workflow maps (this document) |
| Next | Module G (playbooks), then module E (partners) |

## 9. Roadmap modules

### G. CS playbooks (next)

**Problem:** v1 tells a CSM which accounts are at risk and why, but not what to do, and nobody can
see whether anyone acted. Without that, we can't learn which actions save accounts.

**Proposal:**

| ID | Requirement | Priority |
|---|---|---|
| G1 | Map each risk reason to a recommended play, e.g. "seat utilization < 40%" → "enablement session + admin training" | P0 |
| G2 | Create a task when an account becomes High risk, assigned to its CSM, due in 14 days | P0 |
| G3 | CSM logs the action and outcome (contacted, play run, customer response) | P0 |
| G4 | Report: renewal rate of flagged accounts with a play vs without (the "save rate") | P1 |
| G5 | Push tasks to the CRM through the API (a write endpoint) | P2 |

**Data needed:** a `fact_cs_activity` table (account, date, play, outcome). **Main risk:** comparing
accounts with and without a play is biased, because CSMs choose who to help. Start with a small
holdout group (for example 10% of flagged accounts get no automated task) to measure real impact.

### E. Partner channel

**Problem:** some accounts are sold or managed by resellers and implementation partners. If those
accounts churn differently, CS and partner managers need to know which partners need help.

| ID | Requirement | Priority |
|---|---|---|
| E1 | `dim_partner` and a partner link on each account (sourced by, managed by) | P0 |
| E2 | NRR, GRR and health by partner | P0 |
| E3 | Partner scorecard: accounts, ARR, ARR at risk, average health | P1 |
| E4 | Partner filter on Risk List; partner-managed accounts route to the partner manager | P1 |

**Main risk:** small partners have few accounts, so their retention numbers swing a lot. Show
account counts next to every rate and hide rates below a minimum sample size.

## 10. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| CSMs don't trust the score | Not used | Show reasons, keep a simple rule-based score next to the ML score, publish the model card |
| Model leaks future information | Looks great in testing, fails in real life | Snapshot features use only past data; training only on 90+ days before renewal; time-based test split |
| Big accounts flagged just for filing more tickets | Wrong priorities | Tickets per 10 seats instead of raw counts |
| Bad source data | Wrong numbers to leadership | 18 quality checks block the build; dedupe in staging |
| Free hosting sleeps or pauses | Demo fails | Nightly workflow keeps Supabase active; docs explain cold starts |
| Self-fulfilling flags (CS saves the accounts the model flags, so the model looks wrong) | Model degrades over time | Holdout group in module G; retrain with "play run" as a feature |

## 11. Open questions

1. Should the Risk List rank by ARR at risk (revenue-weighted) or by probability (more SMB accounts)? v1 uses ARR at risk; SMB may need its own digital-touch motion instead.
2. Do we need weekly scoring for monthly contracts? Not in this dataset (all annual).
3. Who owns the risk-reason → play mapping in module G: CS Ops or each CS team?
