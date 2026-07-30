# mcp_server/ — MCP Server Layer

**Engine:** Python 3.13, official `mcp` SDK (v1.29.0)
**Server code:** `server.py`
**Local dev transport:** stdio (default) — `python server.py`
**Production transport:** Streamable HTTP — `python server.py --http` (http://127.0.0.1:8000/mcp)

## 🔧 Capability Negotiation

The server declares its capabilities honestly during the `initialize` exchange.
Currently only `tools` (with `listChanged=True` on stdio) is declared — 
elicitation, sampling, resources, and prompts are not declared here because
they are not implemented in this server session.

A client must inspect `result.capabilities` before assuming support for any
feature that hasn't been declared. See `evidence_capability_negotiation.txt`.

## 🛠️ Tools

| Tool | Type | Notes |
|---|---|---|
| `get_dispute_details` | Read-only | dispute_id (string, required) |
| `get_transaction_history` | Read-only | account_id (string, required) |
| `get_merchant_info` | Read-only | merchant_id (string, required) |
| `process_refund` | **Write** | 3-layer defense (schema, business validation, authorization) |
| `escalate_dispute` | **Write, conditional** | Only appears after an escalation trigger fires |

### process_refund — Defensive Design
1. **Schema:** `dispute_id`/`analyst_id` typed strings, required, `additionalProperties: false`
2. **Business validation:** rejects if dispute status is not `open`/`investigating` (no double-refund)
3. **Authorization:** rejects if analyst is `junior` and dispute amount exceeds $500

See `evidence_write_tool_refund.txt` for 4 real captured test cases.

## 🔔 Notifications

Escalation is a property of the **dispute itself** — independent of who's handling it:
- `dispute.amount > $500`, OR
- customer's `risk_flag == 'high'` (joined via disputes → transactions → accounts → customers)

When triggered, the server sends a real `notifications/tools/list_changed` message,
and `escalate_dispute` becomes visible in the **same session**, without reconnecting.

See `evidence_notifications.txt` for a captured before/after tool list.

## 🌐 Transport

- **stdio** (default): single analyst, single machine — used for all local development
- **Streamable HTTP** (`--http` flag): reachable over the network, so multiple analysts
  across different branches can query the same live server simultaneously —
  a setup tied to one local machine can't serve more than one analyst at a time

See `evidence_transport_http.txt` for a captured client session over real HTTP.

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

## Test files

- `test_connection.py` — capability negotiation + read tools
- `test_process_refund.py` — write tool, 3-layer defense (deterministic — resets db state before each run)
- `test_notifications.py` — before/after tool list across an escalation trigger
- `test_http_connection.py` — same tools/flow, verified over Streamable HTTP