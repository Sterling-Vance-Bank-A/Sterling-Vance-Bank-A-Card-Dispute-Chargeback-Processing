# `db/` — Database Layer

**Engine:** SQLite 3  
**Schema:** `schema.sql`  
**Seed data:** `seed.sql`  
**ERD:** `ERD.md`

---

## Why SQLite

The dispute-processing system runs on a single server accessed by a small
team of analysts. SQLite requires zero network configuration, ships with
Python's standard library (`sqlite3`), and stores the entire database in
one file — making it trivial to reset between demo runs and to commit a
known-good state to the repo. For a multi-site deployment the schema is
standard SQL and would port to PostgreSQL with no changes beyond the
`PRAGMA foreign_keys` line.

---

## Files

| File | Purpose |
|------|---------|
| `schema.sql` | Full DDL — all 7 tables, CHECK constraints, indexes |
| `seed.sql` | 2340 rows of deterministic test data (reproducible with `random.seed(42)`) |
| `ERD.md` | Mermaid entity-relationship diagram matching the schema exactly |

---

## Schema overview — 7 tables

| Table | What it models | Key constraint |
|-------|---------------|----------------|
| `customers` | Cardholders | `risk_flag CHECK('normal','elevated','high')` |
| `analysts` | Bank staff | `role CHECK('junior','senior')`, `active CHECK(0,1)` |
| `merchants` | Businesses on statements | `risk_score CHECK BETWEEN 0 AND 100` |
| `accounts` | Credit-card accounts | `status CHECK('active','closed','frozen')` |
| `transactions` | Individual charges | `status CHECK('settled','pending','reversed')` |
| `disputes` | Contested transactions | `UNIQUE(transaction_id)`, `status CHECK(5 values)`, `reason_code CHECK(6 values)` |
| `dispute_history` | Append-only audit log | `outcome CHECK('refunded','denied','escalated')` |

Foreign key enforcement is enabled at the connection level:
```sql
PRAGMA foreign_keys = ON;
```
Every connection that opens the database must run this line — the MCP
server's `db.py` module does this automatically on connect.

---

## How the schema supports each MCP tool

| Tool | Tables touched | Access type |
|------|---------------|-------------|
| `get_dispute` | `disputes`, `transactions`, `merchants`, `customers` | Read |
| `get_customer` | `customers`, `accounts`, `dispute_history` | Read |
| `list_open_disputes` | `disputes`, `transactions` | Read |
| `get_transaction_history` | `transactions`, `accounts`, `merchants` | Read |
| `authenticate_analyst` | `analysts` (flips `active=1`) | Write — fires `tools/list_changed` |
| `process_refund` | `disputes`, `transactions` | Write — elicitation gate at `amount > 500` |
| `escalate_dispute` | `disputes` | Write — senior analyst only |
| `flag_for_fraud_review` | `customers` (sets `risk_flag='high'`) | Write — unlocked by notification |
| `summarize_dispute_evidence` | `disputes`, `merchants` (read-only) | Read — triggers sampling call |
| `generate_dispute_report` | `disputes`, `dispute_history`, `transactions` | Read — progress-tracked |

---

## Seed data — protocol test cases

Every row in `seed.sql` exists because a specific protocol concern needs it.

| ID | What it is | Protocol concern |
|----|-----------|-----------------|
| `DISP-001` | $29.99 duplicate charge, status `open` | **Elicitation** — amount < $500, auto-approves with no pause |
| `DISP-002` | $899.00 unauthorized transaction, status `investigating` | **Elicitation** — amount > $500, `elicitation/create` fires |
| `DISP-003` | status `refunded`, transaction `reversed` | **Defensive design** — second refund attempt rejected |
| `CUST-003` | 4 `dispute_history` rows in last 12 months | **Notifications** — server flips `risk_flag→'high'`, pushes `tools/list_changed` |
| `ANL-001` | role `junior`, `active=0` | **Authorization** — write tools blocked at handler level |
| `ANL-002` | role `senior`, `active=0` | **Notifications** — toggling `active=1` unlocks write tools |
| `MERCH-003` | `risk_score=87` (ShadyDeals.io) | **Sampling** — high-risk merchant feeds `sampling/createMessage` |

The remaining ~2300 rows provide realistic volume for the
`generate_dispute_report` progress-tracking demo and load testing.

---

## Quickstart

```bash
# Create the database from scratch
sqlite3 bank.db < db/schema.sql
sqlite3 bank.db < db/seed.sql

# Verify row counts
sqlite3 bank.db "
SELECT 'customers',       COUNT(*) FROM customers       UNION ALL
SELECT 'analysts',        COUNT(*) FROM analysts        UNION ALL
SELECT 'merchants',       COUNT(*) FROM merchants       UNION ALL
SELECT 'accounts',        COUNT(*) FROM accounts        UNION ALL
SELECT 'transactions',    COUNT(*) FROM transactions    UNION ALL
SELECT 'disputes',        COUNT(*) FROM disputes        UNION ALL
SELECT 'dispute_history', COUNT(*) FROM dispute_history;
"

# Expected output:
# customers|100
# analysts|10
# merchants|20
# accounts|152
# transactions|1283
# disputes|501
# dispute_history|274

# Reset to a clean state
rm bank.db
sqlite3 bank.db < db/schema.sql
sqlite3 bank.db < db/seed.sql
```

> The `bank.db` file is in `.gitignore` — never commit the live database,
> only the SQL source files.
