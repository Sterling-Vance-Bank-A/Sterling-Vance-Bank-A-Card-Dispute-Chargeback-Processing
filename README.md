# Sterling Vance Bank — Card Dispute & Chargeback Processing

## The Company

Sterling Vance Bank is a mid-size consumer credit card issuer. Its dispute team handles hundreds of chargeback cases a day — customers calling to say a charge on their card was fraudulent, duplicated, or never delivered. Every case requires an analyst to look up a transaction, read evidence notes, cross-check merchant history, and decide whether to issue a refund.

Before this system existed, analysts had direct read/write access to the production database. That meant any script, any connected tool, and any LLM assistant talking to that database could approve a $5,000 refund with the same privileges as reading a merchant's name. There were no pauses, no sign-offs, and no audit trail of who approved what and why.

The risk is real: a compromised analyst session, a misconfigured tool, or an overeager model could silently refund thousands of dollars to fraudulent accounts with nothing in the log except a committed SQL row.

---

## The Problem We Solved

We built an MCP server that stands between the AI assistant and the database. The model never touches the database directly — it talks to the server, and the server decides what it's allowed to see and do.

This is not a chatbot. The problem is specifically about **scoped, safe, auditable access to live financial data** — where the stakes of getting it wrong are measured in dollars, not inconvenience. Every protocol concern in this system exists because of a concrete failure mode in the naive version.

---

## Repository Structure

```
db/               Schema, seed data, ERD — the data everyone depends on
mcp_server/       Server code, handlers, tests, evidence logs
agent/            Client that wires to the server, demo scripts, test transcripts
evidence/         Elicitation and sampling evidence logs
README.md         This file
build_db.py       Builds db/sterling_vance.db from schema + seed
check_db.py       Sanity-checks the seeded database
```

---

## Database & ERD

**Engine:** SQLite 3 — embedded, zero configuration, ships with Python's standard library. The entire database state lives in a single file (`sterling_vance.db`), making it trivially reproducible between demo runs.

**7 tables:**

| Table | Purpose |
|---|---|
| `customers` | Cardholders. `risk_flag` field drives the notification trigger |
| `analysts` | Bank staff. `role` field (`junior`/`senior`) drives authorization |
| `merchants` | Businesses. `risk_score` feeds the sampling evidence summary |
| `accounts` | Credit card accounts, linked to customers |
| `transactions` | Individual charges, linked to accounts and merchants |
| `disputes` | One open case per disputed charge. `amount` drives the elicitation trigger |
| `dispute_history` | Append-only audit log of closed cases, used to detect repeat-dispute patterns |

**Key relationships:** customers → accounts → transactions → disputes. `dispute_history` links customers to closed disputes for 12-month pattern detection. Every relationship is enforced with a foreign key. Every fixed-value field is locked with a `CHECK` constraint. `UNIQUE(transaction_id)` on disputes prevents two open cases on the same charge.

See [`db/ERD.md`](db/ERD.md) for the full Mermaid diagram and [`db/schema.sql`](db/schema.sql) for the DDL.

**Seed data** covers every test case each protocol concern depends on:

| Seed ID | State | What it covers |
|---|---|---|
| `DISP-001` | $29.99, `duplicate_charge`, open | Auto-approve path — under threshold |
| `DISP-002` | $899.00, `unauthorized_transaction`, investigating | Elicitation pause — over threshold |
| `DISP-003` | Already `refunded` | Double-refund guard — second attempt rejected |
| `CUST-073` | 35 transactions, 6 with `MERCH-006` | Repeat-pattern slow scan + progress tracking |
| `ANL-001` | Role: `junior` | Authorization failure path |
| `ANL-002` | Role: `senior` | Authorization success path |
| `MERCH-003` | Risk score: 87 (`ShadyDeals.io`) | High-risk merchant for sampling prompt |

---

## Protocol Concerns

### 1. Capability Negotiation
During the `initialize` handshake, the server declares exactly which capabilities it supports — tools (with `listChanged=True`), resources, and prompts. The client reads `result.capabilities` before ever calling a tool that depends on a feature. If a capability isn't declared, the client refuses the call client-side rather than hoping for the best. This is demonstrated in `tc05_missing_capability_blocked.txt`, where the client blocks a call to `process_refund` gated on `elicitation` before any request reaches the server.

### 2. Notifications
When `process_refund` is called on a dispute with `amount > $500` or a customer with `risk_flag = 'high'`, the server pushes a real `notifications/tools/list_changed` message mid-session. The `escalate_dispute` tool — a senior-only action for formally escalating to the card network — appears in the tool list without reconnecting. This is a real runtime state change, not a static tool set. See `tc02_large_dispute_escalation_trigger.txt` for the before/after tool list captured from a live session.

### 3. Elicitation
`process_refund` implements a $500 policy threshold. Refunds at or below $500 execute immediately. Refunds above $500 stop mid-call and return an `elicitation_pause` status — the server is waiting for explicit human sign-off before touching the database. If the analyst approves (`confirmed=True`), the refund proceeds. If the analyst declines (`confirmed=False`), the database state remains strictly unchanged. Both outcomes are captured as separate evidence files. See `evidence/elicitation_approved.txt` and `evidence/elicitation_declined.txt`.

### 4. Sampling
Before the elicitation pause fires on a high-value dispute, `summarize_dispute_evidence` reaches back out to the client's model via `sampling/createMessage`. The server sends the raw `evidence_notes`, merchant name, `risk_score`, and dispute amount, and asks the model to produce a 2-sentence plain-language summary. That summary — not a raw data dump — is what the analyst sees during the sign-off prompt. The model generates the summary; the elicitation consumes it. The exact RPC exchange is captured in `evidence/evidence_sampling_exchange.txt`.

### 5. Resources
The bank's dispute reason-code policy — which reason codes require what evidence, what the card network rules say, and which authority level can approve each — is exposed as a fetchable resource at `policy://disputes/reason-codes`. It's a static document the model can list and read once at session start, then reason over throughout the session. Wrapping it in a tool would imply it changes based on inputs; it doesn't. See `tc06_resource_read.txt`.

### 6. Prompts
The server exposes a `draft_denial_explanation` prompt template. Analysts write denial letters constantly — a parameterized template that just needs a `dispute_id` saves every analyst from re-writing the same instructions from scratch. The template instructs the model to fetch dispute details, read the reason-code policy resource, and draft a clear, empathetic explanation in under 150 words without implying bad faith. See `tc07_prompt_template_used.txt`.

### 7. Transport
**Local development (stdio):** A single analyst on one machine. No networking required. Used for all development and testing.

**Production (Streamable HTTP):** The dispute team has dozens of analysts across different locations who need to connect to the same live server simultaneously. A stdio setup tied to one local machine can only serve one process at a time — it can't handle concurrent analyst sessions from different machines. Streamable HTTP (run with `python mcp_server/server.py --http`, reachable at `http://127.0.0.1:8000/mcp`) solves this. The transition from stdio to HTTP is visible in the commit history as a deliberate, separate step in the project's development.

### 8. Progress Tracking
`scan_repeat_dispute_patterns` scans a customer's full transaction history against a specific merchant, checking for a repeat-dispute pattern. For `CUST-073` this means scanning 35 real transactions one by one. The tool sends a real progress notification per transaction ("Checked 12 of 35 transactions...") so the analyst's interface stays live instead of showing a frozen screen. See `tc04_repeat_pattern_and_slow_scan.txt` for 35 captured progress updates from a real run.

---

## Tool Comparison

| Tool | Type | Elicitation? | Notes |
|---|---|---|---|
| `get_dispute_details` | Read-only | No | Safe at any time |
| `get_transaction_history` | Read-only | No | Safe at any time |
| `get_merchant_info` | Read-only | No | Safe at any time |
| `summarize_dispute_evidence` | Read-only | No | Triggers sampling before elicitation |
| `scan_repeat_dispute_patterns` | Read-only | No | Long-running, sends progress notifications |
| `process_refund` | **Write** | **Yes, above $500** | 3-layer defense: schema → business state → authorization |
| `escalate_dispute` | **Write, conditional** | No | Only available after escalation trigger fires |

**What happens if a client connects without a needed capability:**
If the server does not declare `elicitation` in its capabilities, the client refuses to call `process_refund` gated on that capability client-side — it raises a `PermissionError` before any request reaches the server. The server never assumes a client supports every feature. This is demonstrated in `agent/tc05_missing_capability_blocked.txt`.

---

## How to Run

```bash
# 1. Install dependencies
pip install mcp jsonschema starlette uvicorn

# 2. Build the database
python build_db.py

# 3. Verify the database seeded correctly
python check_db.py

# 4. Run the server (local stdio mode)
python mcp_server/server.py

# 5. Run the agent smoke test (separate terminal)
python agent/agent_client.py

# 6. Generate all demo evidence (all 7 test scenarios)
python agent/run_demo_evidence.py

# Optional: run the server in HTTP mode
python mcp_server/server.py --http
# Then connect a client to http://127.0.0.1:8000/mcp
```

---

## Team Contributions

| Person | Owns |
|---|---|
| Person A | Database design, schema, seed data, elicitation handler, sampling handler |
| Person B | MCP server core, capability negotiation, notifications, transport, defensive tool design |
| Person C | Agent/client, resources, prompts, progress tracking, demo evidence |
