# `db/` — Database Layer & Architecture Guide

**Engine:** SQLite 3  
**Schema DDL:** `schema.sql`  
**Seed Data:** `seed.sql`  
**ERD Diagram:** `ERD.md`

---

## 🛠️ Engine Choice & Justification

The Sterling Vance Bank dispute-processing system runs on SQLite 3.

- **Zero Configuration & Embedded**: Ships with Python's standard library (`sqlite3`), requiring no external database server setup or credentials.
- **Reproducible & Testable**: The entire database state resides in a single file (`bank.db`), making it trivial to wipe and re-seed between demo runs or test executions.
- **Production Portability**: All table definitions use standard ANSI SQL with strict column types and SQL `CHECK` constraints, allowing seamless migration to PostgreSQL or MySQL if scaled to a multi-site enterprise.

> **Crucial Rule**: Foreign key enforcement is enabled on every connection via:
> ```sql
> PRAGMA foreign_keys = ON;
> ```
> The MCP server database connection handler (`mcp_server/db.py`) executes this pragma automatically upon opening the database file.

---

## 📁 Directory Files

| File | Purpose |
|------|---------|
| `schema.sql` | Complete DDL definition for all 7 tables, SQL `CHECK` constraints, and performance indexes. |
| `seed.sql` | 2,340 deterministic rows including baseline protocol test cases (`DISP-001` through `DISP-006`) plus load-test volume. |
| `ERD.md` | Mermaid Entity-Relationship Diagram detailing all 7 entities and their relationships. |

---

## 📋 Table-by-Table Field Reference

### 1. `customers`
> *Cardholders who hold credit card accounts.*

```sql
CREATE TABLE IF NOT EXISTS customers (
    customer_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    phone        TEXT,
    risk_flag    TEXT NOT NULL DEFAULT 'normal'
                     CHECK (risk_flag IN ('normal', 'elevated', 'high')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

| Column | Type | Constraints | Description & Protocol Purpose |
|---|---|---|---|
| `customer_id` | `TEXT` | `PRIMARY KEY` | Unique customer ID (e.g. `CUST-001`). Anchor for accounts and dispute history. |
| `name` | `TEXT` | `NOT NULL` | Customer's full legal name. |
| `email` | `TEXT` | `NOT NULL UNIQUE` | Primary contact email. |
| `phone` | `TEXT` | Optional | Secondary contact phone number. |
| `risk_flag` | `TEXT` | `CHECK('normal', 'elevated', 'high')` | **Notification Trigger Field**: Starts as `'normal'`. When a customer reaches 4+ resolved disputes in 12 months, server updates this to `'high'`, **triggering the `tools/list_changed` notification** to unlock fraud tools. |
| `created_at` | `TEXT` | `DEFAULT datetime('now')` | Registration timestamp. |

---

### 2. `analysts`
> *Bank staff assigned to investigate dispute cases.*

```sql
CREATE TABLE IF NOT EXISTS analysts (
    analyst_id  TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    role        TEXT NOT NULL CHECK (role IN ('junior', 'senior')),
    active      INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1))
);
```

| Column | Type | Constraints | Description & Protocol Purpose |
|---|---|---|---|
| `analyst_id` | `TEXT` | `PRIMARY KEY` | Analyst ID (e.g. `ANL-001` junior, `ANL-002` senior). |
| `name` | `TEXT` | `NOT NULL` | Staff member's name. |
| `email` | `TEXT` | `NOT NULL UNIQUE` | Bank email used for analyst authentication. |
| `role` | `TEXT` | `CHECK('junior', 'senior')` | **Role-Based Authorization**: `'junior'` analysts are restricted to read-only tools. `'senior'` analysts can invoke write tools (`process_refund`, `escalate_dispute`). |
| `active` | `INTEGER` | `CHECK(0, 1)` | **Notification Trigger Field**: `0` = offline, `1` = authenticated. Calling `authenticate_analyst` flips this to `1`, firing `tools/list_changed` to push write capabilities to the active session. |

---

### 3. `merchants`
> *Businesses where card charges occurred.*

```sql
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    risk_score   INTEGER NOT NULL DEFAULT 0 CHECK (risk_score BETWEEN 0 AND 100)
);
```

| Column | Type | Constraints | Description & Protocol Purpose |
|---|---|---|---|
| `merchant_id` | `TEXT` | `PRIMARY KEY` | Merchant ID (e.g. `MERCH-003`). |
| `name` | `TEXT` | `NOT NULL` | Business name (e.g. `ShadyDeals.io`, `Brew & Go Coffee`). |
| `category` | `TEXT` | `NOT NULL` | Merchant sector (`marketplace`, `electronics`, `food_beverage`, etc.). |
| `risk_score` | `INTEGER` | `CHECK(0..100)` | **Sampling Input**: Numerical risk score (0-100). High risk scores (>80) are passed into `sampling/createMessage` prompts so the LLM evaluates merchant credibility when summarizing evidence. |

---

### 4. `accounts`
> *Credit card accounts belonging to customers.*

```sql
CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed', 'frozen')),
    credit_limit REAL NOT NULL CHECK (credit_limit > 0),
    opened_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

| Column | Type | Constraints | Description & Protocol Purpose |
|---|---|---|---|
| `account_id` | `TEXT` | `PRIMARY KEY` | Account ID (e.g. `ACC-001`). Connects customers to transactions. |
| `customer_id` | `TEXT` | `FK -> customers` | Link to `customers.customer_id`. |
| `status` | `TEXT` | `CHECK('active', 'closed', 'frozen')` | Account standing. Frozen accounts block new dispute actions. |
| `credit_limit` | `REAL` | `CHECK(> 0)` | Credit line limit in USD. |
| `opened_at` | `TEXT` | `DEFAULT datetime('now')` | Account opening timestamp. |

---

### 5. `transactions`
> *Individual charges posted to an account.*

```sql
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id  TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts (account_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    merchant_id     TEXT NOT NULL REFERENCES merchants (merchant_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    amount          REAL NOT NULL CHECK (amount > 0),
    txn_date        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'settled' CHECK (status IN ('settled', 'pending', 'reversed'))
);
```

| Column | Type | Constraints | Description & Protocol Purpose |
|---|---|---|---|
| `transaction_id` | `TEXT` | `PRIMARY KEY` | Transaction ID (e.g. `TXN-002`). |
| `account_id` | `TEXT` | `FK -> accounts` | Account charged. |
| `merchant_id` | `TEXT` | `FK -> merchants` | Merchant receiving funds. |
| `amount` | `REAL` | `CHECK(> 0)` | Charge amount in USD. |
| `txn_date` | `TEXT` | `NOT NULL` | Transaction timestamp. Identical dates + amounts indicate duplicate charges. |
| `status` | `TEXT` | `CHECK('settled', 'pending', 'reversed')` | **Defensive Design Guard**: When a refund is processed, status becomes `'reversed'`. If `process_refund` is called again on a `'reversed'` charge, the server rejects it to prevent double refunds. |

---

### 6. `disputes`
> *Core table — open and active chargeback cases.*

```sql
CREATE TABLE IF NOT EXISTS disputes (
    dispute_id           TEXT PRIMARY KEY,
    transaction_id       TEXT NOT NULL UNIQUE REFERENCES transactions (transaction_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    reason_code          TEXT NOT NULL CHECK (reason_code IN ('duplicate_charge', 'item_not_received', 'unauthorized_transaction', 'incorrect_amount', 'service_not_rendered', 'fraud')),
    status               TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'refunded', 'denied', 'escalated')),
    amount               REAL NOT NULL CHECK (amount > 0),
    evidence_notes       TEXT,
    opened_at            TEXT NOT NULL DEFAULT (datetime('now')),
    assigned_analyst_id  TEXT REFERENCES analysts (analyst_id) ON DELETE SET NULL ON UPDATE CASCADE,
    resolved_at          TEXT
);
```

| Column | Type | Constraints | Description & Protocol Purpose |
|---|---|---|---|
| `dispute_id` | `TEXT` | `PRIMARY KEY` | Dispute ID (e.g. `DISP-001`, `DISP-002`). Primary tool parameter. |
| `transaction_id` | `TEXT` | `FK -> transactions UNIQUE` | Enforces **one dispute per transaction**. Prevents duplicate open cases. |
| `reason_code` | `TEXT` | `CHECK(6 values)` | Valid chargeback reasons (`duplicate_charge`, `unauthorized_transaction`, `fraud`, etc.). |
| `status` | `TEXT` | `CHECK(5 values)` | Lifecycle: `open` -> `investigating` -> (`refunded` / `denied` / `escalated`). |
| `amount` | `REAL` | `CHECK(> 0)` | **Elicitation Trigger Field**: Amount disputed. When `process_refund` is called and `amount > 500.00` (e.g. DISP-002 at $899.00), the MCP server calls `elicitation/create` to pause for human approval. |
| `evidence_notes` | `TEXT` | Optional | **Sampling Input**: Free-text investigation notes read by `summarize_dispute_evidence` and sent to `sampling/createMessage`. |
| `opened_at` | `TEXT` | `DEFAULT datetime('now')` | Dispute filing timestamp. |
| `assigned_analyst_id` | `TEXT` | `FK -> analysts` | Staff member assigned to case. |
| `resolved_at` | `TEXT` | Optional | Resolution timestamp populated upon case closure. |

---

### 7. `dispute_history`
> *Append-only audit log of closed disputes.*

```sql
CREATE TABLE IF NOT EXISTS dispute_history (
    history_id   TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    dispute_id   TEXT NOT NULL REFERENCES disputes (dispute_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    outcome      TEXT NOT NULL CHECK (outcome IN ('refunded', 'denied', 'escalated')),
    resolved_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

| Column | Type | Constraints | Description & Protocol Purpose |
|---|---|---|---|
| `history_id` | `TEXT` | `PRIMARY KEY` | Audit record ID (e.g. `HIST-001`). |
| `customer_id` | `TEXT` | `FK -> customers` | Linked customer. Used to count 12-month resolved dispute history. |
| `dispute_id` | `TEXT` | `FK -> disputes` | Linked closed dispute. |
| `outcome` | `TEXT` | `CHECK('refunded', 'denied', 'escalated')` | Terminal outcome. |
| `resolved_at` | `TEXT` | `DEFAULT datetime('now')` | Timestamp for 12-month window queries. |

---

## 🛠️ MCP Tool Mapping

| Tool Name | Database Tables Accessed | Operation Type | Business Function |
|-----------|--------------------------|----------------|-------------------|
| `get_dispute` | `disputes`, `transactions`, `merchants`, `customers` | Read | Fetch complete dispute file |
| `get_customer` | `customers`, `accounts`, `dispute_history` | Read | Fetch customer profile and history |
| `list_open_disputes` | `disputes`, `transactions` | Read | Filter open queue for analyst |
| `get_transaction_history` | `transactions`, `accounts`, `merchants` | Read | Audit past account charges |
| `authenticate_analyst` | `analysts` (flips `active=1`) | Write | Analyst login → **fires `tools/list_changed`** |
| `process_refund` | `disputes`, `transactions` | Write | Refund charge → **elicitation at `amount > 500`** |
| `escalate_dispute` | `disputes` | Write | Senior analyst escalation |
| `flag_for_fraud_review` | `customers` (sets `risk_flag='high'`) | Write | Lock customer → **unlocked by notification** |
| `summarize_dispute_evidence` | `disputes`, `merchants` | Read | Summarize notes → **triggers `sampling/createMessage`** |
| `generate_dispute_report` | `disputes`, `dispute_history`, `transactions` | Read | Export report → **progress-tracked** |

---

## 🧪 Seed Data Test Cases (`db/seed.sql`)

| Test ID | Seed Data State | Protocol Concern Triggered |
|---------|-----------------|---------------------------|
| `DISP-001` | Amount: $29.99, Reason: `duplicate_charge` | **Elicitation (Auto-Approve)**: Amount < $500 executes refund immediately. |
| `DISP-002` | Amount: $899.00, Reason: `unauthorized_transaction` | **Elicitation (Human Pause)**: Amount > $500 calls `elicitation/create`. |
| `DISP-003` | Status: `refunded`, Txn Status: `reversed` | **Defensive Design**: Second refund attempt rejected with zero mutation. |
| `CUST-003` | 4 `dispute_history` rows in 12 months | **Notifications**: Triggers `risk_flag -> 'high'` update and fires `tools/list_changed`. |
| `ANL-001` | Role: `junior`, Active: `0` | **Authorization**: Write tools fail if executed by junior analyst. |
| `ANL-002` | Role: `senior`, Active: `0` | **Notifications**: Toggling `active=1` unlocks write tools dynamically. |
| `MERCH-003` | Risk Score: `87` (ShadyDeals.io) | **Sampling**: High risk merchant feeds LLM sampling prompt for summary. |

---

## ⚡ Database Performance Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_disputes_analyst ON disputes (assigned_analyst_id);
CREATE INDEX IF NOT EXISTS idx_dispute_history_customer ON dispute_history (customer_id, resolved_at);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions (account_id, txn_date);
```

- **`idx_disputes_analyst`**: Speeds up dashboard queries filtering open disputes assigned to a specific analyst.
- **`idx_dispute_history_customer`**: Speeds up 12-month dispute count checks during customer risk flag calculation.
- **`idx_transactions_account`**: Speeds up account statement and transaction history lookups.

---

## 💻 Quickstart & Verification Commands

```bash
# Delete existing database file if present
rm -f bank.db

# Apply schema & seed data
sqlite3 bank.db < db/schema.sql
sqlite3 bank.db < db/seed.sql

# Verify table row counts
sqlite3 bank.db "
SELECT 'customers',       COUNT(*) FROM customers       UNION ALL
SELECT 'analysts',        COUNT(*) FROM analysts        UNION ALL
SELECT 'merchants',       COUNT(*) FROM merchants       UNION ALL
SELECT 'accounts',        COUNT(*) FROM accounts        UNION ALL
SELECT 'transactions',    COUNT(*) FROM transactions    UNION ALL
SELECT 'disputes',        COUNT(*) FROM disputes        UNION ALL
SELECT 'dispute_history', COUNT(*) FROM dispute_history;
"
```
