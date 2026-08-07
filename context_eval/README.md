# Context Window Management — Sterling Vance Bank

## The Problem
Dispute investigation sessions involve 30+ tool calls returning large JSON objects (transaction histories, merchant records, fraud risk scores). Critical early facts (e.g. fraud flags, initial customer disclosures) get buried under hundreds of tokens of JSON noise.

## Test Design
* **Transcript Length**: 40 turns per test transcript.
* **Key Fact Injection**: Fraud flag (`fraud_flag_detected_ACC-021`, risk score 92) appears at Turn 3 (tool output) and Turn 4 (assistant dialogue).
* **Intermediate Noise**: Turns 5–38 contain alternating assistant dialogue and heavy tool-call JSON outputs.
* **Final Probe**: Turn 39/40 queries: *"Before we finalize, was there a fraud flag on the account associated with DISP-073?"*
* **Test Scale**: 10 distinct variations generated deterministically.

## Accuracy & Efficiency Benchmark

| Strategy | Accuracy | Avg Input Tokens | Avg Output Tokens | Avg Latency | Decision |
|---|---|---|---|---|---|
| **Sliding Window (last 10)** | 0/10 | 765 | 219 | 0.0ms | Rejected (loses early critical fraud flag) |
| **Observation Masking (keep 3 tool outputs)** | **10/10** | 765 | **423** | **0.0ms** | **Selected as Primary Strategy** |
| **Recursive Summarization (compact=15)** | 0/10 | 765 | 466 | 0.0ms | Rejected (extractive summary loses exact marker) |
| **Zone-Based Pruning (4 zones)** | 10/10 | 765 | 765 | 0.1ms | Fallback (retains full tokens without masking) |

## Strategy Justification
**Observation Masking** was chosen because Sterling Vance dispute sessions are dominated by tool-call JSON bloat. By masking old tool execution observations while preserving the entire conversational dialogue thread and protected key facts, it achieves **100% accuracy (10/10)** at **45% fewer tokens (423 vs 765)** with **0.0ms latency overhead**.

## How to Run Benchmark
```bash
python context_eval/run_eval.py
```

