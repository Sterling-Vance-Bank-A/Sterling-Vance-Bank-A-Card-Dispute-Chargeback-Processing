# mcp_server/ — MCP Server Layer

**Engine:** Python 3.12+, official `mcp` SDK (v1.29.0+)
**Core Server:** `server.py`
**Local Development Transport:** stdio (default) — `python server.py`
**Production Transport:** Streamable HTTP — `python server.py --http` (listening on `http://127.0.0.1:8000/mcp`)

---

## 🗄️ Database & Schema Integration

**Engine:** SQLite 3 — embedded, single `.db` file (`db/sterling_vance.db`).

The server connects to 7 normalized tables: `customers`, `analysts`, `merchants`, `accounts`, `transactions`, `disputes`, and `dispute_history`.
- Foreign keys enabled (`PRAGMA foreign_keys = ON;`).
- Constraints: `CHECK` constraints on role (`junior`/`senior`), status (`open`/`investigating`/`refunded`/`denied`/`escalated`), and risk flag (`normal`/`elevated`/`high`).
- `UNIQUE(transaction_id)` prevents duplicate open disputes on the same transaction.

---

## 🛠️ Exposed Tools Reference

| Tool | Type | Elicitation? | Auth Check? | Description |
|---|---|:---:|:---:|---|
| `get_dispute_details` | Read-only | No | No | Look up details for a given `dispute_id` |
| `get_transaction_history` | Read-only | No | No | Fetch recent transaction history for an `account_id` |
| `get_merchant_info` | Read-only | No | No | Look up merchant details & risk score by `merchant_id` |
| `summarize_dispute_evidence` | Read-only | No | No | Fetches evidence & triggers `sampling/createMessage` |
| `scan_repeat_dispute_patterns` | Read-only | No | No | Scans transactions for pattern & emits progress notifications |
| `process_refund` | **Write** | **Yes (> $500)** | **Yes (Senior required)** | 3-layer defense: schema → state → RBAC role validation |
| `escalate_dispute` | **Write, Conditional** | No | **Yes (Senior required)** | Only appears in tool list after an escalation trigger fires |

---

## 🛡️ Protocol Features & Handlers

### 1. Capability Negotiation (`initialize`)
Declared capabilities: `tools` (with `listChanged=True`), `resources`, `prompts`.
The server advertises capabilities at session startup so clients can validate support before invoking gated features.

### 2. Human Elicitation (`elicitation_handler.py`)
Bank policy requires explicit human confirmation for high-value refunds:
- **Refunds $\le \$500.00$:** Executed automatically.
- **Refunds $> \$500.00$:** Paused mid-call. Server emits an elicitation request.
  - `confirmed=True` → Refund commits, dispute status updated to `refunded`.
  - `confirmed=False` → Refund cancelled, database state remains **strictly unchanged**.

### 3. LLM Sampling (`sampling_handler.py`)
`summarize_dispute_evidence` constructs a structured prompt from raw dispute notes and merchant risk scores, sending it back to the client via `sampling/createMessage`. The client delegates reasoning to an external model (**OpenRouter / GPT-4o-mini**) and returns a concise summary.

### 4. Policy Resources (`resources.py`)
Exposes dispute reason codes, compliance rules, and approval authority guidelines at `policy://disputes/reason-codes`.

### 5. Prompt Templates (`prompts.py`)
Provides `draft_denial_explanation`. Parameterized by `dispute_id`, it generates structured instructions for drafting compliant customer denial letters.

### 6. Notifications & Dynamic Tool Unlocking
When a refund request touches a dispute $> \$500$ or a customer with `risk_flag == 'high'`, `server.py` emits `await ctx.session.send_tool_list_changed()`. The `escalate_dispute` tool becomes dynamically available in the client's session without reconnecting.

### 7. Real-Time Progress Notifications
`scan_repeat_dispute_patterns` iterates over transaction records and emits `send_progress_notification(progress=i, total=total_txns)` for each transaction checked.

---

## 🧪 Test Suites in `mcp_server/`

```bash
# Run edge case & security vulnerability test suite (11 tests)
python -m unittest mcp_server/test_edge_cases.py

# Run elicitation unit tests (4 tests)
python -m unittest mcp_server/test_elicitation.py

# Run LLM sampling unit tests (2 tests)
python -m unittest mcp_server/test_sampling.py

# Run live stdio server connection test
python mcp_server/test_connection.py

# Run dynamic notification test
python mcp_server/test_notifications.py

# Run process_refund write & auth test
python mcp_server/test_process_refund.py

# Run Streamable HTTP transport test
python mcp_server/test_http_connection.py
```