# Sterling Vance Bank — Database Architecture & Field Guide

This document explains every table, every column, every constraint, and every index in the Sterling Vance Bank Card Dispute database (`db/schema.sql`). It is designed for teammates working on `mcp_server/` (Person B) and `agent/` (Person C) to understand the exact data layout and business logic enforced at the database level.

---

## 🏦 System Overview

Sterling Vance Bank needs to track:
1. **Cardholders (`customers`)** filing chargebacks.
2. **Credit accounts (`accounts`)** and their posted **charges (`transactions`)**.
3. **Disputes (`disputes`)** filed on specific transactions.
4. **Bank staff (`analysts`)** investigating cases.
5. **Businesses (`merchants`)** involved in charges.
6. **Historical outcomes (`dispute_history`)** to detect repeated abuse.

---

## 🔑 Key Database Pragmas & Constraints

- **Foreign Keys Enabled**:
  ```sql
  PRAGMA foreign_keys = ON;
  ```
  *SQLite does not enforce foreign keys by default. Every connection in `mcp_server/db.py` runs this pragma immediately on connect.*

- **Database-Level Enum Enforcement**:
  All status fields, roles, outcomes, and risk levels are locked via SQL `CHECK` constraints. Typos like `'Refunded'` or invalid roles like `'admin'` are rejected at the database engine level.

---

## 📋 Table-by-Table Breakdown

### 1. `customers`
> *Cardholders who hold credit accounts.*

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
| `customer_id` | `TEXT` | `PRIMARY KEY` | Unique customer identifier (e.g. `CUST-001`). Primary anchor for accounts and dispute history. |
| `name` | `TEXT` | `NOT NULL` | Customer's full name, displayed in tool lookups. |
| `email` | `TEXT` | `NOT NULL UNIQUE` | Customer email address. Uniqueness prevents duplicate registrations. |
| `phone` | `TEXT` | Optional | Secondary contact number. |
| `risk_flag` | `TEXT` | `CHECK('normal', 'elevated', 'high')` | **Notification Trigger Field**: Starts at `'normal'`. When a customer accumulates 4+ resolved disputes in 12 months, the server updates this to `'high'`, which **triggers the `tools/list_changed` notification** to unlock fraud tools. |
| `created_at` | `TEXT` | `DEFAULT (datetime('now'))` | Timestamp when the customer record was created. |

---

### 2. `analysts`
> *Bank staff assigned to dispute cases.*

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
| `analyst_id` | `TEXT` | `PRIMARY KEY` | Unique analyst identifier (e.g. `ANL-001` junior, `ANL-002` senior). |
| `name` | `TEXT` | `NOT NULL` | Analyst full name used in audit trail notes. |
| `email` | `TEXT` | `NOT NULL UNIQUE` | Corporate email used for analyst authentication. |
| `role` | `TEXT` | `CHECK('junior', 'senior')` | **Role-Based Authorization**: `'junior'` analysts are restricted to read-only tools. `'senior'` analysts can invoke write tools (`process_refund`, `escalate_dispute`). Handler-level code checks this field. |
| `active` | `INTEGER` | `CHECK(0, 1)` | **Notification Trigger Field**: `0` = offline, `1` = authenticated. Calling `authenticate_analyst` sets this to `1`, which fires `tools/list_changed` to push write capabilities to the active session. |

---

### 3. `merchants`
> *Businesses where transactions occurred.*

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
| `merchant_id` | `TEXT` | `PRIMARY KEY` | Unique merchant identifier (e.g. `MERCH-003`). |
| `name` | `TEXT` | `NOT NULL` | Merchant business name (e.g. `ShadyDeals.io`, `Brew & Go Coffee`). |
| `category` | `TEXT` | `NOT NULL` | Business vertical (`marketplace`, `electronics`, `food_beverage`, etc.). |
| `risk_score` | `INTEGER` | `CHECK(0..100)` | **Sampling Feature Input**: Numerical risk score (0-100). High risk scores (>80) are passed to the `sampling/createMessage` prompt so the model can evaluate merchant credibility when summarizing evidence. |

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
| `account_id` | `TEXT` | `PRIMARY KEY` | Account identifier (e.g. `ACC-001`). Connects customers to transactions. |
| `customer_id` | `TEXT` | `FK -> customers` | Foreign key link to `customers.customer_id`. |
| `status` | `TEXT` | `CHECK('active', 'closed', 'frozen')` | Account standing. Frozen accounts block new dispute actions. |
| `credit_limit` | `REAL` | `CHECK(> 0)` | Total credit line available on the card. |
| `opened_at` | `TEXT` | `DEFAULT (datetime('now'))` | Account opening timestamp. |

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
| `transaction_id` | `TEXT` | `PRIMARY KEY` | Unique transaction ID (e.g. `TXN-002`). |
| `account_id` | `TEXT` | `FK -> accounts` | Account where charge occurred. |
| `merchant_id` | `TEXT` | `FK -> merchants` | Merchant receiving funds. |
| `amount` | `REAL` | `CHECK(> 0)` | Original posted charge amount in USD. |
| `txn_date` | `TEXT` | `NOT NULL` | Date of charge. Shared dates across identical amounts indicate duplicate charges. |
| `status` | `TEXT` | `CHECK('settled', 'pending', 'reversed')` | **Defensive Design Guard**: When a refund is processed, status transitions to `'reversed'`. If `process_refund` is called again on a `'reversed'` transaction, the server rejects it to prevent double refunds. |

---

### 6. `disputes`
> *Core table — contested transactions currently open or investigated.*

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
| `dispute_id` | `TEXT` | `PRIMARY KEY` | Unique dispute ID (e.g. `DISP-001`, `DISP-002`). Core parameter for tool calls. |
| `transaction_id` | `TEXT` | `FK -> transactions UNIQUE` | Enforces **one dispute per transaction** at the database level. Prevents multiple open disputes on a single charge. |
| `reason_code` | `TEXT` | `CHECK(6 values)` | Valid chargeback reasons (`duplicate_charge`, `unauthorized_transaction`, `fraud`, etc.). |
| `status` | `TEXT` | `CHECK(5 values)` | Case lifecycle: `open` -> `investigating` -> (`refunded` / `denied` / `escalated`). |
| `amount` | `REAL` | `CHECK(> 0)` | **Elicitation Trigger Field**: Amount disputed. When `process_refund` is called and `amount > 500.00` (e.g. DISP-002 at $899.00), the MCP server triggers `elicitation/create` to pause for human approval. |
| `evidence_notes` | `TEXT` | Optional | **Sampling Feature Input**: Free-text investigation notes read by `summarize_dispute_evidence` and sent to `sampling/createMessage`. |
| `opened_at` | `TEXT` | `DEFAULT (datetime('now'))` | Filing timestamp. |
| `assigned_analyst_id` | `TEXT` | `FK -> analysts` | Analyst currently handling the dispute. |
| `resolved_at` | `TEXT` | Optional | Timestamp populated when status reaches `refunded`, `denied`, or `escalated`. |

---

### 7. `dispute_history`
> *Append-only audit log of closed disputes per customer.*

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
| `history_id` | `TEXT` | `PRIMARY KEY` | Audit record identifier (e.g. `HIST-001`). |
| `customer_id` | `TEXT` | `FK -> customers` | Linked customer. Used to count 12-month resolved dispute history. |
| `dispute_id` | `TEXT` | `FK -> disputes` | Linked closed dispute. |
| `outcome` | `TEXT` | `CHECK('refunded', 'denied', 'escalated')` | Terminal outcome of the dispute. |
| `resolved_at` | `TEXT` | `DEFAULT (datetime('now'))` | Resolution timestamp used for windowed calculations. |

---

## ⚡ Database Performance Indexes

1. **`idx_disputes_analyst`**: `ON disputes (assigned_analyst_id)`
   - Accelerates analyst dashboard queries ("find all disputes assigned to ANL-002").
2. **`idx_dispute_history_customer`**: `ON dispute_history (customer_id, resolved_at)`
   - Accelerates 12-month dispute count checks during risk flag recalculation.
3. **`idx_transactions_account`**: `ON transactions (account_id, txn_date)`
   - Accelerates transaction history lookups per credit account.

---

## 🧪 Protocol Test Cases in Seed Data (`db/seed.sql`)

| ID | Data State | Protocol Feature Triggered |
|---|---|---|
| `DISP-001` | Amount: $29.99, Reason: `duplicate_charge` | **Elicitation (Auto-Approve)**: Amount < $500 executes refund immediately without pausing. |
| `DISP-002` | Amount: $899.00, Reason: `unauthorized_transaction` | **Elicitation (Human Pause)**: Amount > $500 calls `elicitation/create` for human confirmation. |
| `DISP-003` | Status: `refunded`, Txn Status: `reversed` | **Defensive Tool Design**: Second refund call blocked with zero state mutation. |
| `CUST-003` | 4 `dispute_history` records in 12 months | **Notifications**: Triggers `risk_flag -> 'high'` update and fires `tools/list_changed`. |
| `ANL-001` | Role: `junior`, Active: `0` | **Authorization**: Write tools fail if called by junior analyst. |
| `ANL-002` | Role: `senior`, Active: `0` | **Capability & Notification**: Toggling `active=1` unlocks write tools dynamically. |
| `MERCH-003` | Risk Score: `87` (ShadyDeals.io) | **Sampling**: High risk score is passed into LLM sampling prompt for structured evaluation. |

---

## 🛠️ How to Reset & Run Locally

```bash
# Delete existing database file if present
rm -f bank.db

# Apply schema & seed data
sqlite3 bank.db < db/schema.sql
sqlite3 bank.db < db/seed.sql

# Verify table counts
sqlite3 bank.db "SELECT 'customers', COUNT(*) FROM customers UNION ALL SELECT 'disputes', COUNT(*) FROM disputes;"
```
