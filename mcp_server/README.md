# mcp_server/ — MCP Server Layer

**Engine:** Python 3.13, official `mcp` SDK (v1.29.0)
**Server code:** `server.py`
**Local dev transport:** stdio (default) — `python server.py`
**Production transport:** Streamable HTTP — `python server.py --http` (http://127.0.0.1:8000/mcp)

---

## 🗄️ Database

**Engine:** SQLite 3 — embedded, zero configuration, single `.db` file, ships with Python's standard library.

The database has 7 tables: `customers`, `analysts`, `merchants`, `accounts`, `transactions`, `disputes`, `dispute_history`. Every relationship is enforced with a foreign key (`PRAGMA foreign_keys = ON;`), and every fixed-value field (analyst role, dispute status, risk flag, reason code) is locked down with a `CHECK` constraint at the database level. `UNIQUE(transaction_id)` on disputes prevents two open cases on the same charge.

**Seed data** covers the exact test cases every protocol concern depends on:

| Seed ID | State | What it proves |
|---|---|---|
| `DISP-001` | $29.99, `duplicate_charge`, open | Auto-approve path — under threshold, no pause |
| `DISP-002` | $899.00, `unauthorized_transaction`, investigating | Elicitation pause path — over threshold |
| `DISP-003` | `refunded`, transaction `reversed` | Double-refund guard — second attempt rejected |
| `CUST-003` | 4 resolved disputes in 12 months | Repeat pattern / notification trigger |
| `ANL-001` | Role: `junior` | Authorization check — write tools fail |
| `ANL-002` | Role: `senior` | Authorization check — write tools succeed |
| `MERCH-003` | Risk score: 87 (`ShadyDeals.io`) | High-risk merchant feeding the sampling prompt |

See `db/schema.sql`, `db/seed.sql`, and `db/ERD.md` for the full schema and diagram.

---

## 🔧 Capability Negotiation

The server declares its capabilities honestly during the `initialize` exchange.
Currently only `tools` (with `listChanged=True` on stdio) is declared —
elicitation, sampling, resources, and prompts are not declared here because
they are not implemented in this server session.

A client must inspect `result.capabilities` before assuming support for any
feature that hasn't been declared. See `evidence_capability_negotiation.txt`.

---

## 🛠️ Tools

| Tool | Type | Notes |
|---|---|---|
| `get_dispute_details` | Read-only | dispute_id (string, required) |
| `get_transaction_history` | Read-only | account_id (string, required) |
| `get_merchant_info` | Read-only | merchant_id (string, required) |
| `summarize_dispute_evidence` | Read-only | Fetches raw evidence + calls sampling before elicitation |
| `process_refund` | **Write** | 3-layer defense + elicitation pause above $500 |
| `escalate_dispute` | **Write, conditional** | Only appears after an escalation trigger fires |

### process_refund — Defensive Design & Elicitation

1. **Schema:** `dispute_id`/`analyst_id` typed strings, required, `additionalProperties: false`
2. **Business validation:** rejects if dispute status is not `open`/`investigating` (no double-refund)
3. **Authorization:** rejects if analyst is `junior` and dispute amount exceeds $500

**Elicitation threshold: $500.00** (bank policy limit).

- Refunds **≤ $500.00** execute immediately — no pause, no prompt (e.g. `DISP-001` at $29.99).
- Refunds **> $500.00** stop mid-call and return `elicitation_pause`, waiting for an explicit `confirmed` flag from the analyst.
  - `confirmed=True` → refund proceeds, dispute status updates to `refunded`.
  - `confirmed=False` → refund is blocked, database state remains **strictly unchanged**.

Both outcomes are saved as separate evidence files. See `evidence/elicitation_approved.txt` (approved after pause) and `evidence/elicitation_declined.txt` (declined and blocked).

**Implementation:** `mcp_server/elicitation_handler.py` — `mcp_server/test_elicitation.py` (4 tests, all passing).

See `evidence_write_tool_refund.txt` for 4 real captured test cases.

---

## 🧠 Sampling — Evidence Summarization Before Elicitation

Before the elicitation pause fires, the server reaches back out to the model via `sampling/createMessage` and asks it to turn the raw `evidence_notes` and merchant `risk_score` into a 2-sentence plain-language summary. That summary — not a raw data dump — is what the analyst sees during the sign-off prompt.

This is the server borrowing the model's reasoning mid-task, not the agent having a conversation. The model generates the summary; the elicitation consumes it. Every piece is used by the next.

The exact exchange (what the server sent, what it got back) is saved separately in `evidence/evidence_sampling_exchange.txt`.

**Implementation:** `mcp_server/sampling_handler.py` — `mcp_server/test_sampling.py` (2 tests, all passing).

---

## 🔔 Notifications

Escalation is a property of the **dispute itself** — independent of who's handling it:
- `dispute.amount > $500`, OR
- customer's `risk_flag == 'high'` (joined via disputes → transactions → accounts → customers)

When triggered, the server sends a real `notifications/tools/list_changed` message,
and `escalate_dispute` becomes visible in the **same session**, without reconnecting.

See `evidence_notifications.txt` for a captured before/after tool list.

---

## 🌐 Transport

- **stdio** (default): single analyst, single machine — used for all local development
- **Streamable HTTP** (`--http` flag): reachable over the network, so multiple analysts
  across different branches can query the same live server simultaneously —
  a setup tied to one local machine can't serve more than one analyst at a time

See `evidence_transport_http.txt` for a captured client session over real HTTP.

---

## Running the server

```bash
pip install mcp jsonschema starlette uvicorn

# Build the local SQLite database from schema + seed data first:
python build_db.py

# Local development (stdio):
python mcp_server/server.py

# Production (Streamable HTTP):
python mcp_server/server.py --http
```

---

## Test files

- `test_connection.py` — capability negotiation + read tools
- `test_process_refund.py` — write tool, 3-layer defense (deterministic — resets db state before each run)
- `test_notifications.py` — before/after tool list across an escalation trigger
- `test_http_connection.py` — same tools/flow, verified over Streamable HTTP
- `test_elicitation.py` — elicitation pause, approved path, declined & blocked path (4 tests)
- `test_sampling.py` — sampling prompt construction and evidence summary generation (2 tests)