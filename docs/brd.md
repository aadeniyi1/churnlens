# Business Requirements Document: ChurnLens

| | |
|---|---|
| **Initiative** | Reduce revenue churn with account-level churn intelligence |
| **Author** | Ade (github.com/aadeniyi1) |
| **Sponsor** | VP Customer Success (example role) |
| **Status** | Approved for v1; v1 delivered |
| **Related** | [PRD](prd.md) (what the product does) · [Workflow maps](workflows.md) · [Metrics](metrics.md) |

The BRD explains **why the business needs this and how we'll know it worked**. The PRD explains
**what the product does**. All figures come from ChurnLens's synthetic dataset.

---

## 1. Executive summary

The business has **$41.8M ARR** across about 2,000 customers, but keeps only **84% of its revenue
base each year before expansion (GRR)**. Most churn could be seen coming. Usage drops and support
problems show up about 6 months before renewal, but no team sees all the signals together.

ChurnLens joins contract, usage, support and account data into one warehouse, scores every account
each month, and puts the riskiest accounts in front of customer success with reasons attached.
Today it puts **$5.9M of ARR at risk** in front of the team, spread across 93 high-risk accounts.
Saving one in ten of those dollars is worth about **$590K of ARR per year**, against a tooling cost of $0.

## 2. Business context

### Current state

```
Billing/CRM ──► Finance spreadsheet (NRR/GRR, monthly, manual)
Telemetry   ──► Product team only
Help desk   ──► Support team only
CSMs        ──► Gut feel + renewal calendar; learn about churn at notice
```

**Pain points**

1. **Churn is discovered too late.** CS mostly finds out at renewal notice, when the customer has already decided.
2. **No shared numbers.** Finance, CS and Sales each calculate retention differently.
3. **Effort goes to the wrong accounts.** Each CSM covers about 70 accounts and can't tell which ones matter most this month.
4. **Leadership can't see why.** Churn is reported as one number, without a breakdown by segment, cause or cohort.

### Future state

```
Billing, telemetry, help desk, CRM ──► ChurnLens warehouse (daily) ──► scores + reasons
                                                       │
                       ┌───────────────────────────────┼─────────────────────────────┐
                 Dashboard (CS, execs)          API (CRM, Slack)            Board metrics (NRR, GRR)
```

## 3. Business objectives

| ID | Objective | Measure | Target |
|---|---|---|---|
| BO-1 | Reduce gross revenue churn | 12-month GRR | 84% → 87% within 12 months |
| BO-2 | Catch risk early enough to act | Share of churned ARR flagged 90+ days before renewal | ≥ 60% |
| BO-3 | Focus CS time on revenue at risk | Share of CSM high-touch time on High/Medium accounts | ≥ 50% (needs activity data, module G) |
| BO-4 | One version of retention metrics | Finance and CS report the same NRR/GRR | 100% of board reports use ChurnLens definitions |
| BO-5 | Fix the onboarding gap | First-renewal churn for accounts under 40% early utilization | 34% → 25% |

## 4. Stakeholders

| Stakeholder | Interest | Involvement |
|---|---|---|
| VP Customer Success | Owns GRR; main sponsor | Approves scope, runs the weekly risk review |
| CS managers and CSMs | Daily users | Give feedback on reasons and plays; act on flags |
| CFO / RevOps | Board metrics, forecasting | Signs off metric definitions |
| VP Support | SLA performance | Owns SLA targets and escalation |
| Head of Product | Usage and adoption | Uses usage findings for the onboarding roadmap |
| Data team | Builds and runs the pipeline | Owns data quality and the model |
| IT / Security | Access, secrets | Reviews API keys and hosting |
| Partner managers | Partner-managed accounts | Stakeholders for module E (roadmap) |

## 5. Business requirements

Priority: **Must**, **Should**, **Could** (MoSCoW). "Traces to" points to the matching PRD requirements.

| ID | The business needs... | Priority | Traces to |
|---|---|---|---|
| BR-1 | ...one agreed definition of ARR, NRR, GRR and logo churn, used by every team | Must | A2–A4, [metrics.md](metrics.md) |
| BR-2 | ...retention broken down by segment and signup cohort | Must | A4, A5, D2 |
| BR-3 | ...every current account ranked by revenue at risk, refreshed at least monthly | Must | F3, F5, S1 |
| BR-4 | ...a reason for every flag, in words a CSM can act on | Must | F1, F2 |
| BR-5 | ...flags early enough to act: at least 90 days before renewal | Must | F4 |
| BR-6 | ...to see product adoption (seat use, trend, sticky features) per account | Must | B2–B5 |
| BR-7 | ...to see support experience (SLA breaches, CSAT) per account and how it relates to churn | Must | C2–C4 |
| BR-8 | ...to filter everything by segment, region and CSM, and see parent/child relationships | Must | D1–D3 |
| BR-9 | ...the scores inside existing tools (CRM, Slack), not only in a new dashboard | Should | S2, S3 |
| BR-10 | ...evidence that the model works, in terms leadership understands | Should | F6, Model page |
| BR-11 | ...wrong or incomplete data to be caught before anyone sees it | Must | N3 |
| BR-12 | ...a recommended next step for each flagged account, and a record of what was done | Should | Module G (roadmap) |
| BR-13 | ...retention and risk by partner for partner-sourced accounts | Could | Module E (roadmap) |
| BR-14 | ...a group-level view of risk across a parent company's accounts | Could | D4 |

## 6. Business rules

| ID | Rule |
|---|---|
| RULE-1 | An account churns when its contract ends without a renewal. ARR becomes 0 in the month after the end date |
| RULE-2 | GRR caps each account at its starting ARR, so expansion can't hide churn |
| RULE-3 | NRR and GRR compare ARR today with ARR 12 months ago, for customers who were paying 12 months ago |
| RULE-4 | Risk tier: High if churn probability ≥ 50%, Medium if ≥ 25%, otherwise Low |
| RULE-5 | Health tier: Healthy if score ≥ 70, Watch if 40–69, At risk if < 40 |
| RULE-6 | SLA targets for first response: P1 = 1 hour, P2 = 4 hours, P3 = 24 hours |
| RULE-7 | Seat utilization = monthly active users ÷ licensed seats. Healthy is 55% or more |
| RULE-8 | Scores may use only information available on the scoring date |

## 7. Benefits and costs

**Benefit model** (illustrative, synthetic numbers)

| Driver | Value |
|---|---|
| ARR at risk today (sum of probability × ARR) | $5.9M |
| If CS saves 10% of it | $590K ARR per year |
| If CS saves 20% of it | $1.2M ARR per year |
| GRR impact of saving $590K on a $37M starting base | about +1.6 points |

**Costs for v1**

| Item | Cost |
|---|---|
| Hosting (Supabase, Streamlit Community Cloud, Render free plans) | $0 |
| CI and scheduled runs (GitHub Actions on a public repo) | $0 |
| CS time for the weekly risk review | About 1 hour per week per team (opportunity cost) |

At production scale, expect paid plans for the database and API hosting, plus data engineering time
to connect real source systems instead of synthetic data.

## 8. Scope

**In scope (v1):** modules A (contracts and revenue), B (usage), C (support), D (hierarchy and
segments), F (health score and churn model), dashboard, API.

**Out of scope (v1), on the roadmap:** module E (partner channel), module G (CS playbooks and
activity tracking), automated customer outreach, expansion prediction.

## 9. Assumptions and constraints

**Assumptions**

- Contracts are annual, so churn can only happen at renewal.
- Source systems share one account ID. In real life this needs an ID-mapping step.
- CS has capacity to act on about 10% of accounts each month.
- Synthetic patterns (low usage → higher churn) are realistic enough to show the approach.

**Constraints**

- $0 budget: free hosting tiers only, with their limits (sleeping services, pausing database).
- Must run on an 8 GB laptop, macOS or Windows, without Docker.
- No personal data. All names and companies are fake.

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| CS doesn't adopt the tool | Medium | High | Put scores in the CRM through the API; keep the weekly review short and led by the VP |
| Teams disagree with metric definitions | Medium | Medium | Finance signs off [metrics.md](metrics.md) before go-live |
| Model accuracy drops as behavior changes | Medium | Medium | Model page shows test results; retrain regularly; compare with the rule-based score |
| Flags without follow-up don't reduce churn | High | High | Module G: tasks, plays and a holdout group to measure impact |
| Free-plan limits break the demo | Medium | Low | Nightly job keeps the database active; docs explain cold starts |

## 11. Acceptance criteria

v1 is accepted when:

1. NRR and GRR in the dashboard match a hand calculation on a test dataset (automated test: `tests/test_metrics.py`). ✅
2. Every current account has a churn probability, a health score, and reasons when its score is below Healthy. ✅
3. On renewals the model never saw, the riskiest 10% of accounts hold at least 40% of churned ARR. ✅ 50%
4. All 18 data quality checks pass on every build, and a failed check stops publishing. ✅
5. The dashboard and API are reachable at public URLs, and the API rejects requests without a key. ✅
6. The pipeline runs automatically every night without manual steps. ✅

## 12. Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Sponsor, VP Customer Success | (example) | Approved | |
| CFO / RevOps | (example) | Approved metric definitions | |
| Data lead | Ade | Delivered v1 | |
