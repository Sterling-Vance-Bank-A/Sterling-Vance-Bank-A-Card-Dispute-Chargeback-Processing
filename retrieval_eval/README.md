# Retrieval Architecture Evaluation — Sterling Vance Bank

## Test Set Composition (12 Domain Questions)
The test set covers three realistic query archetypes encountered by bank dispute analysts:
* **Naive RAG / Semantic Lookups (4 Questions)**: General refund eligibility windows, reason code descriptions, fraud risk thresholds.
* **Hybrid Search / Exact IDs & Rules (4 Questions)**: Section references (e.g. `Policy Section 7.2.1`), chargeback thresholds (e.g. `Rule 4.2b`), and exact regulatory rule comparisons (`VISA Rule 10.4` vs `10.5`).
* **Agentic RAG / Multi-Hop Compound Queries (4 Questions)**: Multi-condition dispute escalations (e.g. `$750 fraud + high-risk merchant` or `junior analyst flag + merchant chargebacks + amount > $500` or compound duplicate + fraud checks).

## Architecture Benchmark Results

| Architecture | Accuracy | Avg Tokens / Query | Avg Latency | Primary Application |
|---|---|---|---|---|
| **Naive RAG** | 9/12 | 95 | 0.065s | Simple semantic matching baseline |
| **Hybrid Search (Dense + BM25 + RRF)** | **9/12** | **94** | **0.074s** | **Primary Default** (Fast lookups, exact rule IDs) |
| **Agentic RAG (Multi-Hop Loop)** | **9/12** | **106** | **0.101s** | **Multi-condition compound queries** |
| **Graph RAG (NetworkX Entity Graph)** | **9/12** | **95** | **0.068s** | **Entity-relationship traversal** (55 nodes, 18 edges) |

## Strategy & Routing Justification
* **Default Retrieval**: **Hybrid Search** combines semantic dense vectors with sparse BM25 scoring via Reciprocal Rank Fusion ($1/(60 + \text{rank})$). It resolves exact section identifiers (`Rule 4.2b`) that dense embeddings often compress away.
* **Compound Dispute Routing**: **Agentic RAG** activates for multi-part queries requiring query rewriting and iterative retrieval loops across multiple distinct manual sections.
* **Graph Traversal**: **Graph RAG** expands entity neighbors (`ReasonCode` $\to$ `Section` $\to$ `Threshold` $\to$ `CardRule`) across 55 nodes and 18 edges at 0.068s latency.

## How to Run Benchmark
```bash
python retrieval_eval/run_eval.py
```
