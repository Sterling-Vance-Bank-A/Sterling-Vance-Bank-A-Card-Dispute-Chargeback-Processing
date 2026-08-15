# Agent Layer (`agent/`)

**Sterling Vance Bank Enterprise Agent Suite**  
Provides specialized, modular AI agents and clients interacting over the Model Context Protocol (MCP) server and SQLite database:
1. **`agent_client.py` (`DisputeAgentClient`):** Asynchronous protocol client handling capability negotiation, dynamic tool discovery (`tools/list_changed`), capability gating, and LLM sampling (`sampling/createMessage`).
2. **`memory_agent.py` (`DisputeMemoryAgent`):** Long-term memory & RAG retrieval agent integrating the rolling buffer, scratchpad, episodic store, semantic fact store, and ChromaDB vector store.
3. **`dispute_planning_agent.py` (`DisputePlanningAgent`):** Autonomous multi-step planning and decomposition agent executing dynamic DAGs, algorithmic routing (PS/ToT/LATS), self-correction (SelfRefine/Reflexion), and planning-driven MCP tool execution.
4. **`demo_dispute_planning.py`:** Consolidated demonstration script covering all 5 planning concerns end-to-end.

---

## 📂 File Directory

| File | Subsystem | Description |
|---|---|---|
| `dispute_planning_agent.py` | **Planning & Decomposition** | Autonomous planning agent with Dynamic Decomposition, SubTaskRouter, Grounded LATS, SelfRefine, Reflexion, and MCP tool execution. |
| `demo_dispute_planning.py` | **Planning & Decomposition** | Consolidated 5-part demonstration script (Divergence, Routing, Self-Refine, Reflexion, Grounding). |
| `agent_client.py` | **MCP Client** | Async MCP client with protocol handshake, capability gating, and OpenRouter sampling. |
| `memory_agent.py` | **Memory & RAG** | Multi-session dispute analyst agent with short-term buffer, episodic/semantic memory, and RAG policy lookup. |
| `run_demo_evidence.py` | **MCP Evidence** | Automated scenario runner generating protocol evidence files (`tc01`–`tc08`). |
| `evidence/` | **MCP Traces** | Captured protocol proof files for capability negotiation, notifications, elicitation, and progress tracking. |

---

## 🛠️ Dispute Planning Agent Execution Flow

```
                     Incoming Complex Dispute Request
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │  1. Context Grounding (MCP)   │
                   │   get_dispute_details / merch │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │  2. Dynamic Decomposition DAG │
                   │    (Adaptive step-by-step)    │
                   └───────────────┬───────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Plan-and-Solve   │     │ Tree of Thoughts │     │  Grounded LATS   │
│ (Evidence/Lines) │     │ (Queue Rankings) │     │ (State Actions)  │
└─────────┬────────┘     └────────┬─────────┘     └────────┬─────────┘
          │                       │                        │
          └───────────────────────┼────────────────────────┘
                                  │
                                  ▼
                   ┌───────────────────────────────┐
                   │ 3. Self-Correction & Memories │
                   │  - SelfRefine on disclosures  │
                   │  - Reflexion on high-stakes   │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │ 4. Planning-Driven MCP Action │
                   │   process_refund / escalate   │
                   └───────────────────────────────┘
```

---

## 🚀 Execution Commands

```bash
# 1. Run the Dispute Planning Agent demo (Consolidated 5-part demo)
python agent/demo_dispute_planning.py

# 2. Run planning agent unit tests
python tests/test_dispute_planning_agent.py

# 3. Run MCP client smoke test
python agent/agent_client.py

# 4. Run Memory & RAG agent demo
python memory_rag_demo.py
```