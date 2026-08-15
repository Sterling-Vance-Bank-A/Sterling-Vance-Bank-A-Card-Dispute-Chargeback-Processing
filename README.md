# Sterling Vance Bank — Enterprise AI Agent Platform
## Card Dispute & Chargeback Processing System

An enterprise-grade autonomous AI banking platform built across four integrated layers:
1. **Model Context Protocol (MCP) Server & Client** (`mcp_server/`, `agent/agent_client.py`)
2. **Long-Term Memory Subsystem** (`memory/`, `context_eval/`)
3. **Grounded Policy Retrieval (RAG)** (`rag/`, `retrieval_eval/`)
4. **Task Decomposition, Planning & Self-Correction Engine** (`planning/`, `planning_eval/`, `agent/dispute_planning_agent.py`)

---

## 🏛️ System Architecture

```
Sterling-Vance-Bank/
├── mcp_server/                <- Layer 1: MCP Server (JSON Schema tools, resources, sampling)
│   ├── server.py              7 MCP tools, prompt templates, policy resources
│   └── README.md
├── memory/                    <- Layer 2: Long-Term Memory Subsystem
│   ├── short_term.py          Rolling buffer (max 20) + Scratchpad (never pruned)
│   ├── episodic_store.py      SQLite per-session episodic store (db/memory.db)
│   ├── semantic_store.py      Versioned semantic fact store with conflict resolution
│   ├── router.py              Promote-or-drop buffer overflow router
│   ├── consolidation.py       Periodic semantic consolidation engine
│   └── README.md
├── context_eval/              <- Layer 2: Context Window Management Evaluation
│   ├── strategies/            Sliding Window, Observation Masking, Summarization, Zone Pruning
│   ├── test_suite.py          40-turn long-context transcripts (10 variations)
│   └── run_eval.py            Evaluation runner (Observation Masking chosen: 10/10 acc, 423 tok)
├── rag/                       <- Layer 3: Grounded Policy Retrieval Subsystem
│   ├── corpus/                sterling_vance_policy.txt (Dispute & Chargeback Manual)
│   ├── chunker.py             Section-based + fixed-size chunking
│   ├── vector_store.py        ChromaDB HNSW index with metadata filtering
│   ├── naive_rag.py           Chunk -> Embed -> Retrieve top-k
│   ├── hybrid_search.py       ChromaDB vector + BM25 with Reciprocal Rank Fusion (RRF)
│   ├── agentic_rag.py         Multi-hop retrieval loop (up to 3 hops)
│   ├── graph_rag.py           NetworkX entity graph (ReasonCode -> Section -> Threshold)
│   └── self_rag_verifier.py   Relevance & support verification
├── retrieval_eval/            <- Layer 3: RAG Architecture Evaluation
│   ├── test_questions.py      12 banking policy test questions across 3 complexity classes
│   └── run_eval.py            Evaluation runner (Hybrid Search chosen: 12/12 acc, 1.2ms)
├── planning/                  <- Layer 4: Planning & Decomposition Subsystem
│   ├── algorithms/
│   │   ├── decomposition.py         Decomposition-First (Static DAG, Kahn's cycle check)
│   │   ├── dynamic_decomposition.py Dynamic Decomposition (Adaptive step-by-step loop)
│   │   ├── plan_and_solve.py        Plan-and-Solve (PLAN -> SOLUTION prompting)
│   │   ├── tree_of_thoughts.py      Tree of Thoughts (Generate -> Evaluate -> Beam Search)
│   │   ├── lats.py                  LATS (4-Phase MCTS: Select, Expand, Evaluate, Backprop)
│   │   ├── self_refine.py           Self-Refine (Draft -> Compliance Critic -> Revision)
│   │   ├── reflexion.py             Reflexion (Multi-trial episodic verbal memory loop)
│   │   └── environment.py           GroundedDisputeEnvironment (SQLite validation) vs Ungrounded
│   ├── router.py              SubTaskRouter (Problem-shape algorithmic dispatch)
│   ├── PROBLEM.md             Problem framing & regulatory constraints document
│   ├── demo_divergence.py     Decomposition divergence proof (DISP-003)
│   ├── demo_reflexion.py      Reflexion cross-trial memory proof (DISP-002)
│   ├── demo_grounding.py      Grounded vs Ungrounded LATS contrast
│   └── README.md
├── planning_eval/             <- Layer 4: Planning Test Suite & Benchmark Traces
│   └── test_suite.py          18 fixed test cases across all planning paradigms
├── agent/                     <- Enterprise Agent Implementations
│   ├── agent_client.py        MCP client with capability gating and sampling
│   ├── memory_agent.py        Memory & RAG dispute analyst agent
│   ├── dispute_planning_agent.py Autonomous planning agent with Dynamic DAG & Grounded LATS
│   ├── demo_dispute_planning.py  Consolidated 5-part planning demonstration script
│   └── README.md
├── db/                        <- Databases: sterling_vance.db (core bank) & memory.db (memory)
└── artifacts/                 <- Execution trace logs and comparison tables
```

---

## 🎯 Part 4: Task Decomposition & Planning Subsystem

### 1. The Planning Problem: Multi-Condition Dispute Resolution
In card dispute operations, requests are multi-step and subject to strict federal regulations (Regulation E, 12 CFR § 1005.11), card network rules (VISA 10.4/10.5, Mastercard 4531), analyst dollar authorization thresholds, and merchant risk concentrations.

A single-turn LLM call or single tool execution cannot safely resolve these requests because:
1. **Dynamic Environmental Surprises:** An incoming claim may reference an already-closed or refunded dispute (`DISP-003`). A static plan blindly executes the payout, resulting in illegal duplicate credits.
2. **Ungrounded Hallucinations:** When LLMs self-evaluate actions, they approve unauthorized operations (e.g. junior analysts approving $899 refunds). External grounding in the live database is required.
3. **Multi-Constraint Action Tradeoffs:** Complex merchant portfolios require combinatorial lookahead to optimize statutory recovery timelines before deciding between direct refunds and network escalations.

---

### 2. Task Decomposition: Static DAG vs. Dynamic Adaptive Loop

| Feature | Decomposition-First (`DecompositionFirst`) | Dynamic Decomposition (`DynamicDecomposition`) |
|---|---|---|
| **Execution Model** | Full DAG generated upfront; executed in topological order. | Step-by-step execution interleaved with environment observations. |
| **Acyclicity** | Enforced at construction time using Kahn's algorithm (`validate_acyclic()`). | Dynamically scheduled with dependency validation. |
| **Reaction to Surprises** | Blindly executes pre-computed DAG steps regardless of interim findings. | Observes state mutations and pivots (e.g. halts on terminal dispute status). |

#### Divergence Case (`DISP-003` Terminal Dispute Payout):
* **Scenario:** Customer requests remediation and refund on `DISP-003` ($150.00). Database status is already `'refunded'`.
* **Decomposition-First:** Generated a 4-step plan (`evidence` $\to$ `evaluate` $\to$ `refund` $\to$ `notify`) and blindly attempted to execute an illegal duplicate refund at Step 3.
* **Dynamic Decomposition:** Discovered `status='refunded'` at Step 1, flagged `diverged=True`, cancelled the refund branch, generated a closure audit notice, and safely completed in 2 steps.

---

### 3. Planning Algorithms & Sub-Task Routing Rationale

Each sub-task is routed via `SubTaskRouter` (`planning/router.py`) to the planning algorithm matching its structural complexity:

| Sub-Task Category | Assigned Method | Justification |
|---|:---:|---|
| **Linear Deterministic Tasks**<br>*(Evidence aggregation, exposure calculation, timelines)* | **Plan-and-Solve (PS)** | Single-pass sequential structure. PS generates explicit `PLAN` and `SOLUTION` sections with minimal token overhead (~240 tokens, 1 call). |
| **Combinatorial & Prioritization Tasks**<br>*(Merchant queue ranking, statutory recovery urgency)* | **Tree of Thoughts (ToT)** | Multiple valid permutations exist. ToT explores candidate paths using bounded beam search, self-evaluating each against statutory deadlines. |
| **State-Mutating Actions**<br>*(Direct refunds, network escalations, senior analyst overrides)* | **Grounded LATS** | High-cost actions requiring external feedback. Uses MCTS guided by `GroundedDisputeEnvironment` against SQLite constraints and reflects on failed branches. |
| **Statutory Written Communications**<br>*(Regulation E disclosure letters, compliance notices)* | **Self-Refine** | Single-draft outputs that benefit from an Independent Compliance Critic persona enforcing mandatory Reg E statutory clauses. |
| **High-Stakes Multi-Constraint Tasks**<br>*(Multi-condition dispute remediation)* | **Reflexion** | Retries the entire task across multiple trials within the same run, carrying a capped episodic buffer of verbal reflections from failed attempts to guarantee convergence. |

---

### 4. Grounded vs. Ungrounded Environment

The toolkit's randomized scoring was replaced with `GroundedDisputeEnvironment` connected to `db/sterling_vance.db`:

```
                          ┌───────────────────────────┐
                          │    Candidate Action       │
                          │ "Refund DISP-003 ($150)"  │
                          └─────────────┬─────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                             ▼
  ┌─────────────────────────────┐               ┌─────────────────────────────┐
  │   Ungrounded Environment    │               │ Grounded Dispute Environment│
  │    (Model Self-Opinion)     │               │    (db/sterling_vance.db)   │
  ├─────────────────────────────┤               ├─────────────────────────────┤
  │ Score: 1.0 (APPROVED)       │               │ Score: 0.0 (BLOCKED)        │
  │ Result: ILLEGAL DUPLICATE   │               │ Result: "Refund blocked:    │
  │         PAYOUT EXECUTED     │               │ dispute already terminal    │
  │                             │               │ (refunded)."                │
  └─────────────────────────────┘               └─────────────────────────────┘
```

---

### 5. Cost & Quality Comparison Table (18-Case Test Suite)

Evaluated across the full 18-case benchmark in [`planning_eval/test_suite.py`](file:///c:/Users/omari/PycharmProjects/Sterling-Vance-Bank-A-Card-Dispute-Chargeback-Processing/planning_eval/test_suite.py):

| Method / Subsystem | Category Tested | Task Success | Avg LLM Calls | Avg Tokens | Avg Latency | Est. Cost / Run | Production Role |
|---|---|:---:|:---:|:---:|:---:|:---:|---|
| **Plan-and-Solve** | Linear Sub-tasks | **100%** (5/5) | 1.0 | 240 | 0.01s | $0.0001 | **Default for linear summarization** |
| **Tree of Thoughts** | Combinatorial Ranking | **100%** (5/5) | 3.2 | 620 | 0.03s | $0.0003 | **Default for merchant prioritization** |
| **Ungrounded LATS** | State Actions | **40%** (2/5) | 4.0 | 780 | 0.04s | $0.0004 | *Rejected (hallucinates compliance)* |
| **Grounded LATS** | State Actions | **100%** (5/5) | 4.0 | 820 | 0.04s | $0.0004 | **Default for refunds & escalations** |
| **Self-Refine** | Compliance Disclosures | **100%** (3/3) | 3.0 | 690 | 0.03s | $0.0003 | **Default for customer written notices** |
| **Reflexion** | Multi-Trial Actions | **100%** (3/3) | 4.3 | 940 | 0.05s | $0.0005 | **Default for constraint recovery** |
| **Decomposition-First** | Full Top-Level Plans | **33%** (1/3) | 4.0 | 810 | 0.04s | $0.0004 | *Restricted to static linear cases* |
| **Dynamic Decomposition**| Full Top-Level Plans | **100%** (3/3) | 2.7 | 580 | 0.03s | $0.0003 | **Default top-level decomposition** |

---

## ⚡ Quick Start & Reproduction Commands

### 1. Installation
```bash
git clone https://github.com/Sterling-Vance-Bank-A/Sterling-Vance-Bank-A-Card-Dispute-Chargeback-Processing.git
cd Sterling-Vance-Bank-A-Card-Dispute-Chargeback-Processing
pip install -r requirements.txt
```

### 2. Run Autonomous Planning Agent & Demonstrations
```bash
# Run the consolidated 5-part demonstration script (Divergence, Routing, Self-Refine, Reflexion, Grounding)
python agent/demo_dispute_planning.py

# Run planning agent unit test suite (3/3 passing)
python tests/test_dispute_planning_agent.py

# Run standalone proof scripts
python planning/demo_divergence.py
python planning/demo_reflexion.py
python planning/demo_grounding.py
```

### 3. Run Memory & RAG Demonstration
```bash
# Run end-to-end memory & retrieval demo
python memory_rag_demo.py
```

### 4. Run MCP Protocol Server & Client
```bash
# Run MCP client smoke test
python agent/agent_client.py
```
