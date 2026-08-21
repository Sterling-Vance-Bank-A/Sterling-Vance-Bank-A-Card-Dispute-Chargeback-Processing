# Person A Scope: State Graph Architecture & Crash Durability

This package contains the complete state-graph architecture, checkpointing layer, Human-in-the-Loop (HITL) escalation handler, and failure ticket system required for **Person A (Lead State Graph Architect & Durability Lead)**.

## 📁 Package Structure

```
.
├── db/
│   ├── __init__.py
│   └── schema_extensions.py      # SQLite tables for Checkpoints, HITL Tasks, and Tickets
├── state_graph/
│   ├── __init__.py
│   ├── checkpointer.py           # Durable SQLite Checkpointer (Fixed ORDER BY rowid DESC)
│   ├── hitl_and_tickets.py       # HITL pause triggers and failure ticket handling
│   ├── graph_fraud.py            # Graph 1: Fraud Pre-Arbitration (Constrained ReAct + RAG + Async Wait)
│   ├── graph_remediation.py      # Graph 2: Portfolio Remediation (Task Decomposition DAG + LATS MCTS)
│   └── test_crash_recovery.py    # Process crash & resume test script
└── README.md                     # Documentation and usage guide
```

## 🚀 How to Run Crash & Resume Verification Test
```bash
# Step 1: Execute workflow until process is killed mid-run
python -m state_graph.test_crash_recovery

# Step 2: Resume execution seamlessly from exact saved checkpoint
python -m state_graph.test_crash_recovery --resume
```
