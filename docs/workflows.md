# Workflow maps

How data and people move through ChurnLens. GitHub draws these diagrams automatically from the
text (they're written in [Mermaid](https://mermaid.js.org/)). Click the ⧉ icon on a diagram to open it full size.

1. [System data flow](#1-system-data-flow): from source systems to dashboard and API
2. [Monday risk review](#2-monday-risk-review): how CS uses the Risk List each week
3. [Renewal timeline](#3-renewal-timeline): what happens 120 days before a renewal
4. [Risk reason to action](#4-risk-reason-to-action): which play fits which reason (module G preview)
5. [Support SLA escalation](#5-support-sla-escalation): when a support problem becomes a churn risk
6. [Pipeline and release](#6-pipeline-and-release): how a code change and a nightly refresh reach production
7. [Integration: nightly CRM sync](#7-integration-nightly-crm-sync): how another system pulls scores through the API

---

## 1. System data flow

```mermaid
flowchart LR
    subgraph Sources["Source systems (synthetic, generate/)"]
        CRM[CRM<br/>accounts, hierarchy, CSMs]
        BILL[Billing<br/>contracts, renewals]
        TEL[Product telemetry<br/>1.7M events]
        HD[Help desk<br/>tickets, CSAT]
    end

    subgraph Warehouse["DuckDB warehouse (pipeline/)"]
        STG[Staging<br/>dedupe, clean]
        DIM[Dimensions<br/>account, product, CSM, date]
        FACT[Facts<br/>contract, ARR by month,<br/>usage by day, ticket]
        MART[Marts and metrics<br/>account-month, ARR bridge,<br/>cohorts, NRR/GRR]
        DQ{18 quality<br/>checks}
    end

    subgraph Model["Scoring (model/)"]
        FEAT[Snapshot features<br/>past data only]
        HS[Health score<br/>+ reasons]
        ML[Churn model<br/>gradient boosting]
        SCORE[fact_account_health]
    end

    subgraph Serve["Serving"]
        SB[(Supabase<br/>Postgres)]
        DASH[Streamlit dashboard]
        API[FastAPI on Render]
    end

    CRM & BILL & TEL & HD --> STG --> DIM --> FACT --> MART --> DQ
    DQ -- pass --> FEAT --> HS & ML --> SCORE
    DQ -- fail --> STOP[Build stops,<br/>nothing published]
    SCORE --> SB
    MART --> SB
    SB --> DASH & API
    API --> EXT[CRM, Slack,<br/>other tools]
```

## 2. Monday risk review

```mermaid
flowchart TD
    A([Monday 9:00]) --> B[VP CS opens Risk List<br/>High + Medium, renewing within 6 months]
    B --> C[Sort by ARR at risk]
    C --> D{Account already<br/>has an owner<br/>and a plan?}
    D -- yes --> E[Check last week's action:<br/>did health improve?]
    D -- no --> F[Assign to CSM<br/>in team meeting]
    E --> G{Improving?}
    G -- yes --> H[Keep plan, review next week]
    G -- no --> I[Escalate: exec sponsor<br/>or different play]
    F --> J[CSM opens Account 360]
    J --> K[Read top reasons:<br/>usage, support, contract]
    K --> L[Pick play from<br/>reason → action map]
    L --> M[Contact customer<br/>within 5 business days]
    M --> N[Log action in CRM]
    N --> O([Next month's scores<br/>show the result])
    H --> O
    I --> M
```

## 3. Renewal timeline

The model is trained on snapshots taken 90+ days before renewal, so the first useful flag arrives
around day −120. Each step below is a checkpoint the CSM owns.

```mermaid
flowchart LR
    T120["Day −120<br/>Score reviewed<br/>in Monday meeting"] --> T90["Day −90<br/>Risk plan agreed<br/>if High/Medium"]
    T90 --> T60["Day −60<br/>Value review with customer:<br/>usage, outcomes, roadmap"]
    T60 --> T30["Day −30<br/>Renewal quote sent;<br/>exec call if still High"]
    T30 --> T0{"Day 0<br/>Renewal"}
    T0 -->|renewed / expanded| WIN[Update forecast,<br/>plan expansion]
    T0 -->|contracted| PART[Log reason,<br/>watch next year]
    T0 -->|churned| LOSS[Exit interview,<br/>tag churn reason]
    LOSS --> LEARN[Feeds next model<br/>training run]
    PART --> LEARN
```

## 4. Risk reason to action

This is the core of module G (CS playbooks, roadmap). In v1 the CSM picks the play by hand from
this map.

```mermaid
flowchart TD
    R{Top reason on<br/>the account}
    R -->|"Seat utilization below 55%"| P1[Enablement play:<br/>admin training, usage review,<br/>identify inactive seats]
    R -->|"Usage fell N points in 3 months"| P2[Discovery call:<br/>what changed? new team,<br/>new tool, champion left?]
    R -->|"Recent tickets missed SLA"| P3[Support recovery:<br/>escalate open tickets,<br/>support lead joins call]
    R -->|"Urgent P1/P2 tickets"| P3
    R -->|"Low CSAT"| P4[Service review:<br/>CSM + support lead<br/>walk through recent cases]
    R -->|"Contracted at last renewal"| P5[Exec sponsor play:<br/>business review,<br/>re-confirm value]
    P1 & P2 & P3 & P4 & P5 --> LOG[Log play + outcome<br/>module G: fact_cs_activity]
    LOG --> MEASURE[Save rate by play<br/>vs holdout group]
```

## 5. Support SLA escalation

```mermaid
sequenceDiagram
    participant C as Customer
    participant S as Support
    participant CL as ChurnLens
    participant CSM as CSM
    participant SL as Support lead

    C->>S: Opens P1 ticket
    S-->>C: First response (target: 1 hour)
    Note over S: Response took 3 hours: SLA breached
    S->>CL: Ticket data (nightly)
    CL->>CL: SLA breach rate rises,<br/>support score falls,<br/>reason "missed SLA" added
    CL->>CSM: Account moves to Medium/High<br/>on Monday Risk List
    CSM->>SL: Escalate: account at risk,<br/>renewal in 4 months
    SL->>C: Follow-up call, root cause
    CSM->>C: Check-in, confirm fix
    CL-->>CSM: Next month: support score recovers
```

## 6. Pipeline and release

```mermaid
flowchart TD
    subgraph Change["Code change"]
        DEV[Edit on laptop] --> LOCAL[uv run pytest<br/>uv run ruff check .]
        LOCAL --> PR[Open pull request]
        PR --> CI{GitHub Actions CI:<br/>lint → build 500 accounts<br/>→ quality checks → tests}
        CI -- red --> FIX[Fix and push again] --> CI
        CI -- green --> MERGE[Merge to main]
    end

    subgraph Deploy["Automatic deploys from main"]
        MERGE --> STREAM[Streamlit Cloud<br/>redeploys dashboard]
        MERGE --> RENDER[Render<br/>redeploys API]
    end

    subgraph Nightly["Nightly refresh, 06:00 UTC"]
        CRON([Schedule]) --> BUILD[Build full dataset<br/>+ quality checks + model]
        BUILD --> PUB[Publish tables to Supabase<br/>one transaction]
    end

    PUB --> STREAM
    PUB --> RENDER
```

## 7. Integration: nightly CRM sync

What `examples/client.py` does, and what a real Salesforce or HubSpot sync would do.

```mermaid
sequenceDiagram
    participant J as Sync job (nightly)
    participant API as ChurnLens API
    participant CRM as CRM

    J->>API: GET /status
    API-->>J: ok, scores for 2025-12
    loop Every page of 500 accounts
        J->>API: GET /v1/accounts?limit=500&offset=N<br/>X-API-Key: ••••
        API-->>J: accounts + total
    end
    J->>J: Map fields:<br/>risk_tier → Churn Risk Tier<br/>churn_probability → Churn Probability<br/>reasons[0] → Top Churn Reason
    J->>CRM: Upsert accounts by external ID
    CRM-->>J: Updated
    Note over J,CRM: CSMs see risk on the account page<br/>without opening ChurnLens
```
