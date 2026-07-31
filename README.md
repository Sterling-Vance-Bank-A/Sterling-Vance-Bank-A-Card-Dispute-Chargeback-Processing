# Sterling Vance Bank — Card Dispute & Chargeback Processing

**MCP Server Lab** | Giving an LLM safe, scoped access to bank dispute data via the Model Context Protocol.

---

## 🏦 System Overview

Sterling Vance Bank is a mid-size regional bank whose dispute analysts process hundreds of customer card chargebacks per week. Before this system, analysts had direct SQL access to the production database — creating severe security risks, potential compliance violations, and risk of accidental data corruption.

**Our Solution:** An MCP (Model Context Protocol) server that acts as a secure, policy-enforcing gatekeeper in front of the SQLite dispute database. The LLM (or analyst) interacts strictly through protocol-level tools, resources, and prompts. The server enforces every business rule — role-based access control (RBAC), refund policy thresholds ($500), human sign-off elicitation, and audit logs — before a single row changes in the database.

---

## 🏗️ Architecture

```text
┌────────────────────────────────────────────────────────┐
│  👤 ANALYST / AGENT (Client)                           │
│  agent/agent_client.py                                 │
│  • Handshake negotiation & capability validation       │
│  • Client-side capability gating                       │
│  • OpenRouter LLM Sampling integration                 │
└───────────────────────────┬────────────────────────────┘
                            │  MCP Protocol (stdio / HTTP)
┌───────────────────────────▼────────────────────────────┐
│  🛡️ MCP SERVER (Server Layer)                          │
│  mcp_server/server.py                                  │
│  • 6 Base Tools + 1 Conditional Tool                   │
│  • Policy Resource (policy://disputes/reason-codes)    │
│  • Prompt Template (draft_denial_explanation)          │
│  • $500 Elicitation Gating                             │
│  • Real-time Progress Notifications                    │
└───────────────────────────┬────────────────────────────┘
                            │  Parameterized SQL Queries
┌───────────────────────────▼────────────────────────────┐
│  🗄️ SQLite DATABASE (Data Layer)                      │
│  db/sterling_vance.db                                  │
│  • 7 Tables with CHECK constraints & Foreign Keys      │
│  • 501 Real Dispute Cases                              │
└────────────────────────────────────────────────────────┘
```

---

## 📂 Repository Structure

```text
Sterling-Vance-Bank/
├── build_db.py                         ← Builds & seeds the SQLite database
├── check_db.py                         ← Quick database verification utility
├── evaluation.py                       ← 21-test performance & latency benchmark suite
├── evaluate_all_disputes.py            ← 501-dispute decision accuracy evaluation script
│
├── db/
│   ├── schema.sql                      ← 7 tables with CHECK constraints & foreign keys
│   ├── seed.sql                        ← Seed data covering 501 disputes & test scenarios
│   ├── ERD.md                          ← Mermaid entity-relationship diagram
│   ├── test_db.py                      ← Database unit tests (8 tests)
│   └── sterling_vance.db               ← SQLite production database file
│
├── mcp_server/
│   ├── server.py                       ← Core MCP server (tools, handlers, transport)
│   ├── resources.py                    ← Dispute policy resource handler
│   ├── prompts.py                      ← Denial explanation prompt template handler
│   ├── elicitation_handler.py           ← Human sign-off elicitation handler (> $500)
│   ├── sampling_handler.py             ← LLM evidence summarization handler
│   ├── test_edge_cases.py              ← 11 edge-case & vulnerability defense tests
│   ├── test_connection.py              ← Live stdio server connection test
│   ├── test_notifications.py           ← Dynamic tools/list_changed notification test
│   ├── test_process_refund.py          ← Authorization & refund validation tests
│   ├── test_elicitation.py             ← Elicitation pause unit tests (4 tests)
│   ├── test_sampling.py                ← LLM sampling prompt unit tests (2 tests)
│   └── test_http_connection.py         ← Streamable HTTP transport test
│
└── agent/
    ├── agent_client.py                 ← DisputeAgentClient (full MCP client)
    ├── run_demo_evidence.py            ← 8 automated evidence scenario runners
    ├── .env                            ← OPENROUTER_API_KEY (git-ignored)
    └── evidence/                       ← Evidence output files (tc01 – tc08)
        ├── tc01_handshake_discovery_and_routine_refund.txt
        ├── tc02_large_dispute_escalation_trigger.txt
        ├── tc03_unauthorized_action_blocked.txt
        ├── tc04_repeat_pattern_and_slow_scan.txt
        ├── tc05_missing_capability_blocked.txt
        ├── tc06_resource_read.txt
        ├── tc07_prompt_template_used.txt
        └── tc08_real_llm_sampling.txt
```

---

## 🎯 Protocol Concerns & Features

### 1. Capability Negotiation
During `initialize`, the server declares `tools` (with `listChanged=True`), `resources`, and `prompts`. The client inspects `result.capabilities` before invoking gated features. If the server does not declare `elicitation`, `call_tool_gated()` blocks execution client-side.
- **Evidence:** `agent/evidence/tc05_missing_capability_blocked.txt`

### 2. Real-Time Notifications
When `process_refund` is called on a high-value dispute ($> \$500$) or a high-risk customer (`risk_flag = 'high'`), the server emits a `notifications/tools/list_changed` message. The senior-only `escalate_dispute` tool dynamically appears in the client tool list mid-session without reconnecting.
- **Evidence:** `agent/evidence/tc02_large_dispute_escalation_trigger.txt`

### 3. Human Elicitation
Refunds $\le \$500.00$ execute immediately. Refunds $> \$500.00$ pause execution and return an `elicitation_pause` state. The server waits for explicit human sign-off (`confirmed=True` / `confirmed=False`). Declining a refund keeps database state strictly unchanged.
- **Evidence:** `agent/evidence/tc01...` (auto-approved) & `tc02...` (elicitation pause)

### 4. LLM Sampling (`sampling/createMessage`)
`summarize_dispute_evidence` fetches raw evidence notes, merchant risk score, and dispute amount, sending them to the client's model via `sampling/createMessage`. The client queries **OpenRouter (`openai/gpt-4o-mini`)** to return a 2-sentence plain-language summary for the analyst.
- **Evidence:** `agent/evidence/tc08_real_llm_sampling.txt`

### 5. Policy Resources
Dispute reason codes, card network compliance rules, and authority limits are exposed as a fetchable resource at `policy://disputes/reason-codes`.
- **Evidence:** `agent/evidence/tc06_resource_read.txt`

### 6. Prompt Templates
The server provides a `draft_denial_explanation` prompt template. Given a `dispute_id`, it generates structured instructions for drafting clear, empathetic customer denial letters.
- **Evidence:** `agent/evidence/tc07_prompt_template_used.txt`

### 7. Transport Layer
- **stdio (Local Development):** Default mode for single-analyst local sessions.
- **Streamable HTTP (Production):** `python mcp_server/server.py --http` listening on `http://127.0.0.1:8000/mcp` for concurrent multi-branch analyst sessions.

### 8. Real-time Progress Tracking
`scan_repeat_dispute_patterns` scans transaction histories (e.g. 35 transactions for `CUST-073`) and emits live progress notifications (`progress=i, total=35`) to keep the UI interactive.
- **Evidence:** `agent/evidence/tc04_repeat_pattern_and_slow_scan.txt`

---

## 📊 Evaluation & Performance Benchmarks

### 1. Protocol & Performance Benchmark (21 Tests)
Run via `python evaluation.py`:

```text
=========================================================================================================
Test                                                 Category                      Latency  Status
=========================================================================================================
handshake_cold_start                                 Capability Negotiation       1278.3ms  [PASS]
tool_discovery_6_tools                               Capability Negotiation       1278.3ms  [PASS]
capability_elicitation_not_declared_by_server        Capability Negotiation          0.0ms  [PASS]

get_dispute_details_DISP001                          Read Tools                      3.6ms  [PASS]
get_dispute_details_not_found                        Read Tools                      2.6ms  [PASS]
get_transaction_history_ACC001                       Read Tools                      3.1ms  [PASS]
get_merchant_info_MERCH001                           Read Tools                      2.4ms  [PASS]
get_merchant_info_not_found                          Read Tools                      4.8ms  [PASS]

notification_tools_list_changed                      Notifications                 295.6ms  [PASS]

auth_junior_blocked_large_refund                     Authorization                   5.1ms  [PASS]
auth_junior_blocked_from_escalate                    Authorization                   2.9ms  [PASS]

elicitation_routine_auto_approved                    Elicitation                    18.9ms  [PASS]
elicitation_pause_over_threshold                     Elicitation                     4.1ms  [PASS]

resource_list                                        Resources & Prompts             1.3ms  [PASS]
resource_read_policy                                 Resources & Prompts             1.9ms  [PASS]
prompt_list                                          Resources & Prompts             1.4ms  [PASS]
prompt_get_denial_template                           Resources & Prompts             2.9ms  [PASS]

progress_scan_repeat_patterns                        Progress Tracking              20.0ms  [PASS] (35 updates)
throughput_10_sequential_reads                       Throughput                      2.6ms  [PASS] (377.64 calls/sec)

llm_sampling_call_latency                            End-to-End Workflow             4.0ms  [PASS]
start_to_finish_full_workflow_latency                End-to-End Workflow          1715.4ms  [PASS]
=========================================================================================================

Pass Rate: 21/21 (100.0%) | Average Tool Call Latency: 2.6 ms | Sequential Throughput: ~377 calls/sec
```

---

### 2. All-Database Decision Accuracy Evaluation (501 Disputes)
Run via `python evaluate_all_disputes.py`:

```text
================================================================================
 🏆 STERLING VANCE BANK — ALL-DATABASE DECISION EVALUATION REPORT
================================================================================
 Total Disputes Evaluated          : 501
 Total Decision Checks Executed    : 1002 (Senior + Junior)
 Evaluation Runtime                : 6.67 seconds (13.31 ms / dispute)
--------------------------------------------------------------------------------
 🟢 Senior Analyst Decision Accuracy : 501 / 501  (100.0%)
 🟢 Junior Analyst Decision Accuracy : 501 / 501  (100.0%)
 🎯 OVERALL SYSTEM DECISION ACCURACY  : 100.0%
================================================================================
```

---

### 3. Edge Cases & Vulnerability Defense Suite (11 Tests)
Run via `python -m unittest mcp_server/test_edge_cases.py`:

| Edge Case / Vulnerability | Test Outcome | Defense Enforced |
|---|:---:|---|
| Exact $500.00 Boundary | ✅ **PASS** | Auto-approved (at/under threshold) |
| $500.01 Boundary | ✅ **PASS** | Triggers elicitation pause for senior approval |
| SQL Injection Payload | ✅ **PASS** | Parameterized SQL prevents database corruption |
| Malformed Dispute ID | ✅ **PASS** | Handled safely without server exception |
| Non-Existent Dispute ID | ✅ **PASS** | Returns clean `"No dispute found"` message |
| Non-Existent Analyst ID | ✅ **PASS** | Rejected with `"Analyst ANL-99999 not found"` |
| Double-Refund Guard | ✅ **PASS** | Re-refunding `refunded` dispute is blocked |
| Denied-Case Guard | ✅ **PASS** | Re-refunding `denied` dispute is blocked |
| Invalid Resource URI | ✅ **PASS** | Raises structured JSON-RPC error |
| Prompt Missing ID | ✅ **PASS** | Interpolates missing IDs safely |
| Zero-Match Pattern Scan | ✅ **PASS** | Returns `count=0, pattern=False` cleanly |

---

## 🛠️ How to Run

### 1. Installation
```bash
pip install mcp openai python-dotenv starlette uvicorn anyio jsonschema
```

### 2. Build & Verify Database
```bash
python build_db.py
python check_db.py
```

### 3. Run Full Demo Evidence Suite (All 8 Scenarios)
```bash
python agent/run_demo_evidence.py
```

### 4. Run System Benchmarks & Evaluations
```bash
# Protocol & Latency Benchmark (21 tests)
python evaluation.py

# Full Database Decision Accuracy Evaluation (501 disputes)
python evaluate_all_disputes.py

# Edge Case & Security Vulnerability Suite (11 tests)
python -m unittest mcp_server/test_edge_cases.py
```

### 5. Production Streamable HTTP Mode
```bash
# Terminal 1: Start Server over HTTP
python mcp_server/server.py --http

# Terminal 2: Test HTTP Client Connection
python mcp_server/test_http_connection.py
```

---

## 👥 Team Contributions

| Team Member | Domain & Ownership |
|---|---|
| **Person A** | Database architecture (`db/`), SQLite schema, seed generation, elicitation handler, sampling handler |
| **Person B** | Core MCP Server (`mcp_server/server.py`), capability negotiation, notifications, HTTP transport, defensive tools, policy resources, prompt templates |
| **Person C** | Dispute Agent Client (`agent/agent_client.py`), demo evidence runner (`run_demo_evidence.py`), test scenarios `tc01`–`tc08` |
