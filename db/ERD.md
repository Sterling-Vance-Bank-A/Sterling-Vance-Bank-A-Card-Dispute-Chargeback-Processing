# Entity-Relationship Diagram — Dispute & Chargeback Database

```mermaid
erDiagram
    customers ||--o{ accounts : "has"
    customers ||--o{ dispute_history : "accumulates"
    accounts ||--o{ transactions : "has"
    merchants ||--o{ transactions : "involved_in"
    transactions ||--o| disputes : "may_have"
    analysts ||--o{ disputes : "assigned_to"
    disputes ||--o| dispute_history : "resolves_into"

    customers {
        text customer_id PK
        text name
        text email
        text phone
        text risk_flag
        text created_at
    }

    analysts {
        text analyst_id PK
        text name
        text email
        text role
        int active
    }

    merchants {
        text merchant_id PK
        text name
        text category
        int risk_score
    }

    accounts {
        text account_id PK
        text customer_id FK
        text status
        real credit_limit
        text opened_at
    }

    transactions {
        text transaction_id PK
        text account_id FK
        text merchant_id FK
        real amount
        text txn_date
        text status
    }

    disputes {
        text dispute_id PK
        text transaction_id FK
        text reason_code
        text status
        real amount
        text evidence_notes
        text opened_at
        text assigned_analyst_id FK
        text resolved_at
    }

    dispute_history {
        text history_id PK
        text customer_id FK
        text dispute_id FK
        text outcome
        text resolved_at
    }
```

## Relationship notes
- A **customer** has many **accounts**, and separately accumulates many **dispute_history** rows over time.
- An **account** has many **transactions**.
- A **merchant** is involved in many **transactions**.
- A **transaction** may have **zero or one dispute** (not every charge is disputed).
- An **analyst** is assigned to many **disputes**.
- A resolved **dispute** produces one **dispute_history** row for that customer.