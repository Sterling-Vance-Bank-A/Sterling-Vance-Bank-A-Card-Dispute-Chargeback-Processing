# Agent & Client Layer (`agent/`)

**Role:** Dispute Agent Client, Protocol Negotiation, LLM Sampling Integration, & Demo Evidence Suite.

---

## 🛠️ Overview & Key Components

The `agent/` module contains the client-side implementation of the Sterling Vance Dispute Processing system:
- **`agent_client.py` (`DisputeAgentClient`):** Asynchronous MCP client wrapping stdio and HTTP sessions. Performs protocol capability negotiation during `initialize`, maintains dynamic tool discovery (`tools/list_changed`), enforces client-side capability gating, and integrates OpenRouter sampling callbacks.
- **`run_demo_evidence.py`:** Automated scenario runner executing 8 test cases (`tc01` – `tc08`) and populating the `agent/evidence/` directory with verified protocol traces.

---

## 📂 File Directory

| File | Description |
|---|---|
| `agent_client.py` | `DisputeAgentClient` class with capability negotiation, `call_tool_gated()`, resource/prompt methods, and OpenRouter sampling. |
| `run_demo_evidence.py` | 8 automated evidence scenario runners that reset test DB rows and generate trace outputs. |
| `evidence/` | Directory containing captured proof files (`tc01` through `tc08`) for all protocol concerns. |

---

## 📄 Evidence File Reference (`agent/evidence/`)

| File | Protocol Concern Proved | Description |
|---|---|---|
| `tc01_handshake_discovery_and_routine_refund.txt` | **Capability Negotiation & Elicitation** | Opening handshake, dynamic tool discovery, and auto-approved refund ($\le \$500.00$). |
| `tc02_large_dispute_escalation_trigger.txt` | **Notifications & Elicitation Pause** | Refund $> \$500$ fires `tools/list_changed` notification unlocking `escalate_dispute` and triggering elicitation pause. |
| `tc03_unauthorized_action_blocked.txt` | **Authorization & RBAC** | Junior analyst (`ANL-001`) attempted refund/escalation rejected server-side. |
| `tc04_repeat_pattern_and_slow_scan.txt` | **Progress Tracking** | Long-running transaction scan (`CUST-073` / `MERCH-006`) sending 35 live progress updates. |
| `tc05_missing_capability_blocked.txt` | **Capability Gating** | Client refuses client-side to call tool requiring unadvertised capabilities (`PermissionError`). |
| `tc06_resource_read.txt` | **Resources** | Reading policy guidelines from `policy://disputes/reason-codes`. |
| `tc07_prompt_template_used.txt` | **Prompts** | Fetching parameterized `draft_denial_explanation` prompt template for `DISP-003`. |
| `tc08_real_llm_sampling.txt` | **Sampling (`sampling/createMessage`)** | `summarize_dispute_evidence` invoking client OpenRouter LLM (`openai/gpt-4o-mini`) for AI evidence summary. |

---

## 🛠️ Tool Capabilities & Policy Matrix

| Tool Name | Type | Elicitation Threshold | Authorization Rule |
|---|---|:---:|---|
| `get_dispute_details` | Read-only | None | Safe for all analyst roles |
| `get_transaction_history` | Read-only | None | Safe for all analyst roles |
| `get_merchant_info` | Read-only | None | Safe for all analyst roles |
| `summarize_dispute_evidence` | Read-only | None (Triggers Sampling) | Safe for all analyst roles |
| `scan_repeat_dispute_patterns` | Read-only | None (Progress Tracked) | Safe for all analyst roles |
| `process_refund` | **Write** | **Pause at $> \$500.00$** | **Senior Analyst Required** for $> \$500$ |
| `escalate_dispute` | **Write** | None | **Senior Analyst Required** |

---

## 🚀 Execution Commands

```bash
# Run agent smoke test (Handshake + tool discovery + DISP-001 lookup)
python agent/agent_client.py

# Run full demo evidence suite (Generates all 8 evidence files in agent/evidence/)
python agent/run_demo_evidence.py
```