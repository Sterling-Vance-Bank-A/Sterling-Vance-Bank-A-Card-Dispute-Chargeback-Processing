# Database Layer (`db/`)

**Engine:** SQLite 3 (embedded database)  
**Database File:** `db/sterling_vance.db`  
**Schema DDL:** `db/schema.sql`  
**Seed Data:** `db/seed.sql`  
**ERD Diagram:** `db/ERD.md`

---

## 🛠️ Design Rationale & Engine Choice

The Sterling Vance Bank dispute-processing system relies on an embedded SQLite 3 engine:
- **Zero Configuration:** Native integration via Python's standard `sqlite3` module.
- **Data Integrity:** Strict SQL `CHECK` constraints, primary keys, and foreign keys (`PRAGMA foreign_keys = ON;`).
- **Reproducible Test State:** Deterministic seed file (`db/seed.sql`) populates 501 disputes across customers, merchants, and transactions.

---

## 📁 Table Definitions & Schema Summary

| Table Name | Primary Key | Foreign Keys | Key Constraints & Purpose |
|---|---|---|---|
| `customers` | `customer_id` | None | `CHECK(risk_flag IN ('normal', 'elevated', 'high'))`. Cardholder profiles. |
| `analysts` | `analyst_id` | None | `CHECK(role IN ('junior', 'senior'))`. Analyst access control. |
| `merchants` | `merchant_id` | None | `CHECK(risk_score BETWEEN 0 AND 100)`. Merchant risk assessment. |
| `accounts` | `account_id` | `customer_id` | `CHECK(status IN ('active', 'closed', 'frozen'))`. Customer credit accounts. |
| `transactions` | `transaction_id` | `account_id`, `merchant_id` | `CHECK(status IN ('settled', 'pending', 'reversed'))`. Posted transactions. |
| `disputes` | `dispute_id` | `transaction_id` (UNIQUE) | `CHECK(status IN ('open', 'investigating', 'refunded', 'denied', 'escalated'))`. Active dispute cases. |
| `dispute_history` | `history_id` | `customer_id`, `dispute_id` | `CHECK(outcome IN ('refunded', 'denied', 'escalated'))`. Audit log of resolved cases. |

---

## 🧪 Key Seed Case Profiles (`db/seed.sql`)

| Case ID | Amount | Reason Code | Customer / Risk | Purpose & Protocol Trigger |
|---|---|---|---|---|
| `DISP-001` | $29.99 | `duplicate_charge` | `CUST-001` (normal) | **Routine Auto-Approved Refund**: Under $500 threshold, executes immediately. |
| `DISP-002` | $899.00 | `unauthorized_transaction` | `CUST-002` (normal) | **Elicitation & Notification Trigger**: Amount $> \$500$, triggers elicitation pause and dynamic tool unlocking (`escalate_dispute`). |
| `DISP-003` | $450.00 | `fraud` | `CUST-003` (elevated) | **Double-Refund & Denial Prompt**: Closed dispute preventing duplicate refunds. |
| `CUST-073` | — | — | 35 transactions | **Progress Tracking**: Scan target for `scan_repeat_dispute_patterns` sending 35 live progress updates. |
| `ANL-001` | — | Role: `junior` | Staff | **Junior Role RBAC**: Unauthorized to approve refunds $> \$500$ or escalate cases. |
| `ANL-002` | — | Role: `senior` | Staff | **Senior Role RBAC**: Authorized to approve high-value refunds (with elicitation sign-off) and network escalations. |

---

## 🛠️ Management Commands

```bash
# Build SQLite database from schema and seed data
python build_db.py

# Verify database table row counts
python check_db.py

# Run database unit test suite (8 tests)
python -m unittest db/test_db.py
```
