*/# Person C — Agent/Client, Resources, Prompts, Progress, Demo Evidence

## What's here

| File | Part |
|---|---|
| `agent_client.py` | Part 1 — the agent/client (handshake, live tool discovery, capability gate) |
| `mcp_server/resources.py` | Part 2 — the dispute reason-code policy, as a fetchable resource |
| `mcp_server/prompts.py` | Part 3 — the `draft_denial_explanation` prompt template |
| `mcp_server/server.py` | Part 4 — `scan_repeat_dispute_patterns` (the slow tool), added into the existing dispatch; also now registers resources/prompts |
| `run_demo_evidence.py` | Part 5 — runs all fixed test scenarios, saves each as a distinct file under `evidence/` |

## Setup (from scratch, one time)

```bash
# from the repo root
pip install mcp jsonschema starlette uvicorn
python build_db.py          # builds db/sterling_vance.db from schema + seed
python check_db.py          # sanity check — should print 5 disputes
```

## Run the agent smoke test (Part 1's "what to prove")

```bash
python agent_client.py
```
This connects, prints the handshake (server capabilities), discovers tools,
and runs one read-only call (`get_dispute_details` on `DISP-001`) end to end.

## Generate all demo evidence (Part 5)

```bash
python run_demo_evidence.py
```
This is re-runnable any time — it resets the DB rows each scenario depends
on before running, so results are identical every time. It writes 7 files
into `evidence/`, covering:

- handshake + live discovery + a routine small-dispute refund
- a large dispute that triggers escalation (`tools/list_changed` fires)
- an unauthorized attempt (junior analyst tries the senior-only escalation tool)
- a customer with a repeat-dispute pattern **and** the slow tool (same tool —
  see note below)
- a client refusing, client-side, to use a tool gated on a capability
  (`elicitation`) the server never declared
- a resource being read (the reason-code policy)
- a prompt template being used (`draft_denial_explanation`)


## Tool Comparison

| Tool | Type | Requires Elicitation? | Notes |
|---|---|---|---|
| `get_dispute_details` | Read-only | No | Retrieves dispute information only. |
| `get_merchant_info` | Read-only | No | Retrieves merchant information only. |
| `get_transaction_history` | Read-only | No | Retrieves transaction history only. |
| `scan_repeat_dispute_patterns` | Read-only | No | Performs analysis only; does not modify system state. |
| `process_refund` | Write | Not currently implemented | Changes dispute state by approving a refund. The current server implementation does not perform an elicitation/confirmation step. |
| `escalate_dispute` | Write | No | Escalates a dispute. Access is controlled by analyst role rather than elicitation. |

## Capability Negotiation

The client performs capability negotiation during the MCP `initialize` handshake.

If a tool depends on a capability that the connected server does not advertise (for example, `elicitation`), the client refuses to invoke that tool locally before sending any request to the server. This behavior is demonstrated in `tc05_missing_capability_blocked.txt`.

## Data used in the demo (for reference)

- `CUST-073` has 35 transactions total, 6 of them with `MERCH-006` — the
  repeat-pattern/slow-scan scenario.
- `DISP-001` ($29.99, open) and `DISP-002` ($899, investigating) are the
  small/large dispute pair used throughout — same ones Person B's own
  tests already rely on.
- `ANL-001` (Sarah Kim, junior) and `ANL-002` (James Okafor, senior).