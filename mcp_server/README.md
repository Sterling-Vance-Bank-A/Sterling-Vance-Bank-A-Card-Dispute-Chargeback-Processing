# `mcp_server/` — MCP Server Layer Architecture & Reference Guide

**Engine:** Python 3.12+ | Official `mcp` SDK (v1.29.0+)  
**Server Script:** `mcp_server/server.py`  
**Local Development Transport:** stdio (default) — `python mcp_server/server.py`  
**Production Remote Transport:** Streamable HTTP — `python mcp_server/server.py --http` (`http://127.0.0.1:8000/mcp`)

---

## 🏛️ Server Architecture & Lifecycle

The `mcp_server/` directory contains the core gatekeeper layer for Sterling Vance Bank's dispute processing data. It sits between the client/agent layer and the underlying SQLite database (`db/sterling_vance.db`).

```text
┌────────────────────────────────────────────────────────┐
│  👤 CLIENT / AGENT LAYER (DisputeAgentClient)           │
│  • Discovers tools, resources, & prompts dynamically   │
│  • Listens for notifications/tools/list_changed        │
│  • Handles elicitation pauses & LLM sampling requests  │
└───────────────────────────┬────────────────────────────┘
                            │  MCP Protocol (stdio / HTTP)
┌───────────────────────────▼────────────────────────────┐
│  🛡️ MCP SERVER LAYER (mcp_server/server.py)             │
│  ├── tool dispatch & input schema validation           │
│  ├── mcp_server/elicitation_handler.py ($500 limit)   │
│  ├── mcp_server/sampling_handler.py (LLM summary)     │
│  ├── mcp_server/resources.py (policy:// URI)           │
│  └── mcp_server/prompts.py (draft_denial_explanation) │
└───────────────────────────┬────────────────────────────┘
                            │  Parameterized SQL Queries
┌───────────────────────────▼────────────────────────────┐
│  🗄️ SQLite DATA LAYER (db/sterling_vance.db)           │
└────────────────────────────────────────────────────────┘
```

### 🔄 Version Backward-Compatibility Helper
To ensure the server runs seamlessly across all versions of the `mcp` Python SDK (including older versions that use `app.request_handlers` or `app._request_handlers` instead of `app.add_request_handler`), every module registers handlers using a robust fallback helper:

```python
def _register(method_name, req_type, handler):
    if hasattr(app, "add_request_handler"):
        app.add_request_handler(method_name, req_type, handler)
    elif hasattr(app, "_request_handlers"):
        app._request_handlers[req_type] = handler
    elif hasattr(app, "request_handlers"):
        app.request_handlers[req_type] = handler
```

---

## 🛠️ Complete Tool Specification & Schema Reference

All tools enforce strict JSON Schema validation with `type: "object"`, explicit `required` parameter arrays, exact regex `pattern` matching, and `additionalProperties: false`.

### 1. `get_dispute_details` (Read-only)
Fetches complete dispute records including reason code, amount, status, evidence notes, and customer link.
```json
{
  "type": "object",
  "properties": {
    "dispute_id": {
      "type": "string",
      "description": "The dispute ID to look up, e.g. 'DISP-001'"
    }
  },
  "required": ["dispute_id"],
  "additionalProperties": false
}
```

### 2. `get_transaction_history` (Read-only)
Retrieves posted charge history for a specific credit card account.
```json
{
  "type": "object",
  "properties": {
    "account_id": {
      "type": "string",
      "description": "The account ID to query, e.g. 'ACC-001'"
    }
  },
  "required": ["account_id"],
  "additionalProperties": false
}
```

### 3. `get_merchant_info` (Read-only)
Queries merchant business details, risk scores (0–100), and merchant category.
```json
{
  "type": "object",
  "properties": {
    "merchant_id": {
      "type": "string",
      "description": "The merchant ID to query, e.g. 'MERCH-001'"
    }
  },
  "required": ["merchant_id"],
  "additionalProperties": false
}
```

### 4. `summarize_dispute_evidence` (Read-only / LLM Sampling Trigger)
Fetches raw evidence notes, merchant risk score, and dispute amount, then triggers `sampling/createMessage` back to the client's model (**OpenRouter / GPT-4o-mini**) to generate an executive evidence summary.
```json
{
  "type": "object",
  "properties": {
    "dispute_id": {
      "type": "string",
      "description": "The dispute ID to summarize"
    }
  },
  "required": ["dispute_id"],
  "additionalProperties": false
}
```

### 5. `scan_repeat_dispute_patterns` (Read-only / Progress Tracked)
Scans a customer's transaction history against a specific merchant to detect repeat dispute patterns. Sends live progress notifications (`progress=i, total=N`) for every transaction scanned.
```json
{
  "type": "object",
  "properties": {
    "customer_id": {
      "type": "string",
      "description": "The customer ID to scan, e.g. 'CUST-073'"
    },
    "merchant_id": {
      "type": "string",
      "description": "The merchant ID to check against, e.g. 'MERCH-006'"
    }
  },
  "required": ["customer_id", "merchant_id"],
  "additionalProperties": false
}
```

### 6. `process_refund` (Write Tool / Elicitation Gated)
Processes a chargeback refund on a disputed transaction. Enforces a 3-layer defensive system:
- **Schema Validation:** Regex pattern `^DISP-\d{3,}$` and `^ANL-\d{3,}$`.
- **Business State Validation:** Rejects refund if dispute status is already `refunded` or `denied`.
- **Authorization & Elicitation:** Junior analysts (`ANL-001`) are hard-blocked from approving refunds $> \$500$. Senior analysts (`ANL-002`) attempting refunds $> \$500.00$ trigger an **Elicitation Pause**, requiring explicit human sign-off (`confirmed=True`).

```json
{
  "type": "object",
  "properties": {
    "dispute_id": {
      "type": "string",
      "pattern": "^DISP-\\d{3,}$",
      "description": "The dispute ID to process, e.g. 'DISP-001'"
    },
    "analyst_id": {
      "type": "string",
      "pattern": "^ANL-\\d{3,}$",
      "description": "The analyst approving the refund, e.g. 'ANL-001' or 'ANL-002'"
    }
  },
  "required": ["dispute_id", "analyst_id"],
  "additionalProperties": false
}
```

### 7. `escalate_dispute` (Write Tool / Conditional Visibility)
Formally escalates a dispute to card network arbitration. Dynamically added to the tool list when a high-value dispute ($> \$500$) or high-risk customer (`risk_flag == 'high'`) is processed in the session.
```json
{
  "type": "object",
  "properties": {
    "dispute_id": {
      "type": "string",
      "pattern": "^DISP-\\d{3,}$",
      "description": "The dispute ID to escalate, e.g. 'DISP-001'"
    },
    "analyst_id": {
      "type": "string",
      "pattern": "^ANL-\\d{3,}$",
      "description": "The senior analyst performing escalation, e.g. 'ANL-002'"
    }
  },
  "required": ["dispute_id", "analyst_id"],
  "additionalProperties": false
}
```

---

## 🎯 Protocol Concerns & Code Locations

### 1. Capability Negotiation (`server.py`)
- **Code Path:** `run_stdio()` & `run_http()` in `mcp_server/server.py`.
- **Behavior:** Declares `tools` (`listChanged=True`), `resources`, and `prompts` capabilities during `initialize`.

### 2. Notifications & Dynamic Tool Unlocking (`server.py`)
- **Code Path:** `handle_call_tool` branch for `process_refund` in `mcp_server/server.py`.
- **Behavior:** Triggers `await ctx.session.send_tool_list_changed()`. Pushes dynamic update so `escalate_dispute` becomes visible mid-session.

### 3. Human Elicitation (`elicitation_handler.py`)
- **Code Path:** `process_refund_with_elicitation()` in `mcp_server/elicitation_handler.py`.
- **Behavior:** Refunds $\le \$500.00$ execute immediately. Refunds $> \$500.00$ pause mid-call and prompt the analyst. `confirmed=False` blocks refund and leaves DB state strictly unchanged.

### 4. LLM Sampling (`sampling_handler.py`)
- **Code Path:** `summarize_dispute_evidence()` in `mcp_server/sampling_handler.py`.
- **Behavior:** Calls `ctx.session.create_message()` (`sampling/createMessage`) to request an LLM summary from the client's OpenRouter model (`openai/gpt-4o-mini`).

### 5. Policy Resources (`resources.py`)
- **Code Path:** `register_resources()` in `mcp_server/resources.py`.
- **Behavior:** Exposes `policy://disputes/reason-codes` via `resources/list` and `resources/read`.

### 6. Prompt Templates (`prompts.py`)
- **Code Path:** `register_prompts()` in `mcp_server/prompts.py`.
- **Behavior:** Exposes `draft_denial_explanation` via `prompts/list` and `prompts/get`.

### 7. Transport Layer Options (`server.py`)
- **Local Dev (stdio):** `python mcp_server/server.py` (Default IO pipe).
- **Production (Streamable HTTP):** `python mcp_server/server.py --http` (Starlette + Uvicorn web server listening on `http://127.0.0.1:8000/mcp`).

### 8. Real-time Progress Tracking (`server.py`)
- **Code Path:** `handle_call_tool` branch for `scan_repeat_dispute_patterns` in `mcp_server/server.py`.
- **Behavior:** Emits `await ctx.session.send_progress_notification(progress_token=progress_token, progress=i, total=total_txns)`.

---

## 🧪 Server Test Suites & Verification

Run tests from the repository root:

```bash
# 1. Edge case & security vulnerability test suite (11 tests, 100% pass)
python -m unittest mcp_server/test_edge_cases.py

# 2. Elicitation pause unit tests (4 tests, 100% pass)
python -m unittest mcp_server/test_elicitation.py

# 3. LLM sampling unit tests (2 tests, 100% pass)
python -m unittest mcp_server/test_sampling.py

# 4. Live stdio server connection test
python mcp_server/test_connection.py

# 5. Dynamic tool notification test
python mcp_server/test_notifications.py

# 6. Refund authorization & state check test
python mcp_server/test_process_refund.py

# 7. Streamable HTTP transport test (requires server running with --http)
python mcp_server/test_http_connection.py
```