# Sterling Vance Bank -- Memory & RAG Lab

**Branch:** `memory-rag-lab` | **Extends:** MCP Server Lab (same `mcp_server/`, `db/`)

---

## The Problem

### Problem 1 -- The Agent Forgets Everything Between Sessions

Sterling Vance dispute analysts review multi-session fraud cases. When a senior analyst returns
to DISP-073 the next morning after escalating it the day before, the agent has zero memory of:
- What evidence was already retrieved (transaction history, merchant risk score)
- The analyst's working conclusion ("likely card-not-present fraud, awaiting network response")
- That the dispute was already escalated (so it should not be re-escalated)

For $500+ high-risk cases requiring mandatory human sign-off (elicitation), this stateless
re-narration creates compliance exposure. **Forgetting costs real money.**

### Problem 2 -- The Agent Hallucinates Dispute Policy

The Sterling Vance *Dispute & Chargeback Operations Manual* (50+ pages) lives entirely outside
the database: reason code definitions (4853, 4855, 4863, 4837), VISA/Mastercard rules
(10.4, 10.5, 4531), refund eligibility windows, escalation procedures, authorization thresholds.

When an analyst asks "what is the refund window for reason code 4853?", the agent either
refuses or fabricates a plausible-sounding but wrong answer.
**A fabricated policy answer in dispute resolution is a regulatory violation.**

---

## Architecture

```
Sterling-Vance-Bank/
├── memory/                    <- NEW: long-term memory subsystem
│   ├── short_term.py          Rolling buffer (max 20) + Scratchpad (never pruned)
│   ├── episodic_store.py      SQLite-backed per-session episode log
│   ├── semantic_store.py      Versioned fact store (updates, conflict resolution)
│   ├── router.py              Promote-or-drop: FORGET or EPISODIC only
│   └── consolidation.py       Periodic semantic consolidation pass
├── context_eval/              <- NEW: context window management
│   ├── strategies/
│   │   ├── sliding_window.py
│   │   ├── observation_masking.py
│   │   ├── recursive_summarization.py
│   │   └── zone_pruning.py
│   ├── test_suite.py          40-turn long-context transcripts (10 variations)
│   └── run_eval.py
├── rag/                       <- NEW: retrieval subsystem
│   ├── corpus/sterling_vance_policy.txt   Dispute & Chargeback Operations Manual
│   ├── chunker.py             Section-based + fixed-size chunking
│   ├── vector_store.py        ChromaDB HNSW, cosine similarity, metadata index
│   ├── naive_rag.py           Chunk -> embed -> retrieve top-k
│   ├── hybrid_search.py       Vector + BM25 with RRF fusion
│   ├── agentic_rag.py         Multi-hop reasoning loop (up to 3 hops)
│   ├── graph_rag.py           entity graph (ReasonCode -> Section -> Threshold)
│   └── self_rag_verifier.py   Relevance + support checks
├── retrieval_eval/            <- NEW: retrieval architecture evaluation
│   ├── test_questions.py      12 domain-specific questions
│   └── run_eval.py
├── agent/memory_agent.py      <- NEW: memory + RAG wired into agent loop
├── memory_rag_demo.py         <- NEW: end-to-end demo (every concern fires)
├── mcp_server/                <- REUSED unchanged
└── db/                        <- REUSED; memory.db added alongside sterling_vance.db
```

---

## Context Window Management

### Test Design

40-turn synthetic transcript for dispute DISP-073:
- **Turn 3**: Tool output contains fraud flag (`fraud_flag_detected_ACC-021`, risk_score=92)
- **Turn 4**: Assistant dialogue echoes the fraud flag into the conversational thread
- **Turns 5-38**: 17 tool-call JSON outputs (transaction histories, merchant records) burying the key fact
- **Turn 39**: Analyst asks "Was there a fraud flag on the account?"
- **Accuracy**: Does the pruned transcript still contain `fraud_flag_detected_ACC-021`?

10 variations with different tool output values (deterministic random seed per variation).

### Comparison Table

| Strategy                              | Accuracy | Avg Input Tokens | Avg Output Tokens | Avg Latency |
|---------------------------------------|----------|------------------|-------------------|-------------|
| Sliding Window (last 10)              | 0/10     | 765              | 219               | 0.0ms       |
| Observation Masking (keep 3 outputs)  | 10/10    | 765              | 423               | 0.0ms       |
| Recursive Summarization (compact=15)  | 0/10     | 765              | 466               | 0.0ms       |
| Zone-Based Pruning (4 zones)          | 10/10    | 765              | 765               | 0.1ms       |

### Chosen Strategy: Observation Masking

Both Observation Masking and Zone-Based Pruning achieve 10/10 accuracy. Sliding Window fails
because it drops turns 0-29 entirely, losing the early fraud flag. Recursive Summarization
fails without an LLM (extractive fallback does not preserve the exact marker string).

Observation Masking wins over Zone-Based Pruning on **output tokens (423 vs 765)** -- it
achieves the same accuracy by keeping the full dialogue thread (where turn 4 preserves the
fact) while masking old tool JSON. Zone-based pruning keeps everything, producing a 765-token
context when 423 tokens suffice.

Sterling Vance sessions are **tool-output bloated** (each tool call returns 200-500 token JSON).
Observation masking targets exactly this bloat while preserving the conversational thread.

---

## Retrieval Architecture

### Corpus

Sterling Vance *Dispute & Chargeback Operations Manual* -- 44 chunks, 6,107 characters, indexed
in ChromaDB (HNSW, cosine similarity, `all-MiniLM-L6-v2` embeddings).

Metadata per chunk: `{section, doc_type, reason_code, page_estimate, char_offset}` -- enables
pre-search filtering (e.g., retrieve only chunks tagged `reason_code=4853`).

### Test Questions (12)

| ID  | Question                                                                  | Expected Winner |
|-----|---------------------------------------------------------------------------|-----------------|
| Q01 | Standard refund window for duplicate charge disputes?                     | Naive RAG       |
| Q02 | What does reason code 4853 say about services not rendered?               | Naive RAG       |
| Q03 | Refund eligibility for unauthorized transaction disputes?                  | Naive RAG       |
| Q04 | How do fraud risk scores affect escalation routing?                       | Naive RAG       |
| Q05 | What does Policy Section 7.2.1 say exactly?                               | Hybrid          |
| Q06 | Chargeback threshold in Rule 4.2b?                                        | Hybrid          |
| Q07 | VISA Rule 10.4 vs 10.5 -- when does each apply?                           | Hybrid          |
| Q08 | Exact policy wording for "unauthorized transaction"?                      | Hybrid          |
| Q09 | $750 fraud + high-risk merchant: escalation steps + documentation?        | Agentic RAG     |
| Q10 | Junior flags + prior chargebacks + amount > $500: what policy?            | Agentic RAG     |
| Q11 | Section 3 + Section 9 sign-off for denial > $1000?                       | Agentic RAG     |
| Q12 | Senior analyst sequence for compound (duplicate + fraud) dispute?         | Agentic RAG     |

### Comparison Table

| Architecture                    | Accuracy | Avg Tokens/Query | Avg Latency |
|---------------------------------|----------|------------------|-------------|
| Naive RAG                       | 9/12     | 95               | 0.065s      |
| Hybrid Search (vector+BM25)     | 9/12     | 94               | 0.074s      |
| Agentic RAG (multi-hop)         | 9/12     | 106              | 0.101s      |
| Graph RAG                       | 9/12     | 95               | 0.068s      |

### Chosen Architecture: Hybrid Search (default) + Agentic RAG (multi-hop)

Sterling Vance analysts ask two types of questions during live dispute review:
1. **Quick policy lookups** (reason code windows, exact section references) -- Hybrid Search wins:
   vector finds semantic context, BM25 finds exact IDs like "4.2b" and "Section 7.2.1" that
   do not embed distinctively. Naive RAG misses these.
2. **Multi-condition compound queries** requiring multiple policy sections -- Agentic RAG handles
   these via multi-hop retrieval (0.101s latency vs 0.074s for hybrid).

Graph RAG achieves fast latency (0.068s) via graph expansion across 55 nodes and 18 entity edges,
and is routed for cross-entity queries (reason code -> policy section -> threshold). Hybrid ships as the default; agentic/graph
route compound and entity-relationship queries respectively.

---

## Memory Concerns

### Short-Term Buffer + Scratchpad

`memory/short_term.py`:
- `RollingBuffer(maxlen=20)`: deque of message dicts. When full, oldest item is routed by
  `PromoteOrDropRouter` before the new item is pushed.
- `Scratchpad`: separate dict (`plan`, `sub_goal`, `working_state`, `active_dispute_id`,
  `active_analyst_id`, `notes`). **Never touched by buffer pruning.** Survives the session intact.

### Promote-or-Drop Routing

`memory/router.py` fires on buffer overflow. Scores each aging item by:
- Recency (0.3 weight): newer items score higher
- Entity tags (0.4 weight): items tagged `dispute_id`, `analyst_id`, `fraud_flag`, `amount`
- Content weight (0.3 weight): items containing `DISP-`, `fraud`, `escalat`, `refund`

**Decision logged to `memory/router_decisions.log`** with:
`timestamp | session | turn | score | decision | content_preview`

**This router NEVER writes to semantic memory** -- only FORGET or PROMOTE to episodic store.

### Semantic Memory Consolidation

`memory/consolidation.py` is a **genuinely separate, periodic pass** (not write-time, not
triggered by the router). It:
1. Scans `episodic_store` for episodes older than 24 hours
2. Extracts structured facts using regex patterns
3. Calls `semantic_store.upsert_fact()` -- handles updates, versioning, expiration, conflict

**Real conflict demonstrated:**
- Episode A (Day 1): `MERCH-004 risk_score = 45` (initial onboarding assessment)
- Episode B (Day 3): `MERCH-004 risk_score = 92` (after fraud investigation)
- Consolidation detects conflict -- deprecates v1 (`status='deprecated'`, `deprecated_at=now`),
  installs v2=92 as active, records `conflict_note`.
- Old fact preserved with full version history -- never silently overwritten.

### Self-RAG Verification

`rag/self_rag_verifier.py` applied before any answer reaches the analyst:
1. **Relevance check**: keyword overlap between query and retrieved chunks (threshold 0.15).
   If fails -- re-retrieve or return "not found in policy"
2. **Support check**: keyword overlap between answer and context (threshold 0.10).
   If fails -- return grounded refusal
3. **Memory recall check**: applied to episodic/semantic facts before injecting into agent context

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Build ChromaDB index (first run downloads sentence-transformers model ~80MB)
python -c "from rag.vector_store import get_store; get_store(reset=True)"

# 3. Run context window evaluation (produces comparison table)
python -m context_eval.run_eval

# 4. Run retrieval architecture evaluation (produces comparison table)
python -m retrieval_eval.run_eval

# 5. Run full end-to-end demo (every concern fires)
python memory_rag_demo.py
```

---

## Conflict Resolution Demo

Run: `python -m memory.consolidation`

Or in Python:
```python
import sys; sys.path.insert(0, '.')
from memory.episodic_store import EpisodicStore
from memory.semantic_store import SemanticStore
from memory.consolidation import ConsolidationEngine
ep = EpisodicStore()
sem = SemanticStore()
eng = ConsolidationEngine(ep, sem)
result = eng.demonstrate_real_conflict()
print(result)
```
