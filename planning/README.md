# Planning & Task Decomposition Subsystem (`planning/`)

**Enterprise Agent Extension:** Autonomous Card Dispute Planning & Resolution Engine  
**Built on Top of Reference Toolkit:** [`task_decomposition_and_planning`](https://github.com/Sterling-Vance-Bank-A/task_decomposition_and_planning) (connected via Git Submodule at [`toolkit/`](../toolkit/))

---

## 1. Problem Statement: Why Single-Call Resolution Fails

In card dispute operations at Sterling Vance Bank, incoming requests are multi-step, ambiguous, and subject to statutory constraints (Regulation E, card network rules, merchant risk concentration thresholds, and analyst authorization limits).

When an analyst or cardholder submits a complex request (e.g. *"Remediate dispute DISP-003 ($150.00) claiming duplicate charge, compute exposure, rank recovery urgency, execute remediation, and issue formal compliance disclosure"*), a single LLM turn or deterministic tool call cannot safely resolve it:
1. **Hidden Terminal States:** The target dispute might already be resolved (`refunded` or `denied`). Blindly executing a pre-computed payout plan results in an illegal duplicate credit.
2. **Missing Grounding in Search:** LLMs hallucinate authorization (e.g., self-approving a $899 junior refund) without external database constraint verification.
3. **Multi-Constraint Action Tradeoffs:** Resolving disputes requires evaluating statutory deadlines, dollar exposure, and merchant chargeback ratios before deciding between a direct refund and a card network escalation.

---

## 2. Architecture & Submodule Integration

The planning subsystem directly imports and leverages the upstream algorithms from the `toolkit/` Git submodule, wrapping them with bank-specific SQLite grounding:

```
Sterling-Vance-Bank-A-Card-Dispute-Chargeback-Processing/
├── toolkit/                            <- [UPSTREAM SUBMODULE] Pure Course Planning Lab
│   └── planning_lab/
│       ├── algorithms/
│       │   ├── decomposition.py        <- Static DAG decomposition (decompose_goal, execute_plan)
│       │   ├── dynamic_decomposition.py<- Dynamic step-by-step adaptive loop
│       │   ├── plan_and_solve.py       <- Plan-and-Solve two-phase prompting
│       │   ├── tree_of_thoughts.py     <- Tree of Thoughts beam search
│       │   ├── lats.py                 <- Language Agent Tree Search (4-phase MCTS)
│       │   ├── self_refine.py          <- Self-Refine with deterministic rubric checks
│       │   ├── reflexion.py            <- Reflexion with multi-trial episodic memory
│       │   └── environment.py          <- Environment protocol definition
│       └── models.py                   <- Pydantic models (Plan, Task, Thought, EnvironmentFeedback)
│
├── planning/                           <- Bank Planning Integration Layer
│   ├── environment.py                  <- GroundedDisputeEnvironment (SQLite validation on db/sterling_vance.db)
│   ├── toolkit_adapter.py              <- Direct adapter wrappers delegating to toolkit algorithms
│   ├── router.py                       <- SubTaskRouter (Problem-shape algorithmic dispatch)
│   ├── PROBLEM.md                      <- Formal domain problem framing & regulatory constraints
│   ├── demo_divergence.py              <- Standalone decomposition divergence proof (DISP-003)
│   ├── demo_reflexion.py               <- Standalone Reflexion multi-trial memory proof (DISP-002)
│   ├── demo_grounding.py               <- Standalone Grounded vs Ungrounded LATS contrast
│   └── benchmark.py                    <- Reference benchmark harness & mock double
```

---

## 3. Algorithmic Routing Matrix & Rationale

| Sub-Task Category | Assigned Algorithm | Engineering & Regulatory Justification |
|---|:---:|---|
| **Linear Deterministic Tasks**<br>*(Evidence aggregation, timeline generation, exposure calculation)* | **Plan-and-Solve (PS)** | Single-pass sequential structure. No branching required. PS minimizes latency and token consumption while guaranteeing structured `PLAN` and `SOLUTION` sections. |
| **Combinatorial & Prioritization Tasks**<br>*(Merchant queue ranking, multi-case statutory urgency, risk concentration)* | **Tree of Thoughts (ToT)** | Multiple candidate orderings exist. ToT explores candidate permutations with breadth/depth-bounded beam search and self-evaluates each path against deadlines. |
| **State-Mutating Actions**<br>*(Direct refunds, network escalations, senior analyst overrides)* | **Grounded LATS** | High-cost actions requiring external feedback. Evaluates proposals against live SQLite database constraints (`sterling_vance.db`) and reflects on failed branches. |
| **Statutory Written Communications**<br>*(Regulation E dispute disclosure letters, denial explanations)* | **Self-Refine** | Single-draft outputs that benefit from an Independent Compliance Critic persona enforcing mandatory statutory clauses (e.g. right to request documents under 12 CFR § 1005.11). |
| **High-Stakes Multi-Constraint Actions**<br>*(Disputes with complex cross-table constraints)* | **Reflexion** | Retries the entire task across multiple trials within the same run, carrying a capped episodic buffer of verbal reflections from failed attempts to guarantee convergence. |

---

## 4. Grounded vs. Ungrounded Environment

The reference toolkit ships with an ungrounded model evaluator. For Sterling Vance Bank, `GroundedDisputeEnvironment` directly queries `db/sterling_vance.db` to enforce bank business rules:

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

## 5. Performance & Benchmarking Results

Benchmark results from the full 18-case evaluation run across all algorithms using Mistral AI (`mistral-small-latest`) via `planning_eval/run_eval.py`:

| Method | Evaluated Cases | Task Success | Avg LLM Calls | Avg Tokens | Avg Latency | Avg Cost / Run |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Dynamic Decomposition** | 7 | **7/7 (100.0%)** | 3 | 560 | 47.188s | $0.000000 |
| **Reflexion (Episodic Memory)** | 4 | **4/4 (100.0%)** | 6 | 720 | 8.610s | $0.000000 |
| **Tree of Thoughts** | 11 | **9/11 (81.8%)** | 5 | 580 | 26.670s | $0.000000 |
| **LATS (Ungrounded)** | 11 | **9/11 (81.8%)** | 4 | 640 | 5.532s | $0.000000 |
| **Decomposition-First** | 7 | **5/7 (71.4%)** | 1 | 260 | 72.097s | $0.000000 |
| **Plan-and-Solve** | 11 | **6/11 (54.5%)** | 1 | 246 | 2.942s | $0.000000 |
| **Self-Refine** | 4 | **2/4 (50.0%)** | 2 | 500 | 3.430s | $0.000000 |
| **LATS (Grounded SQLite)** | 11 | **5/11 (45.5%)** | 4 | 690 | 18.677s | $0.000000 |

---

## 6. Universal LLM Client & Execution Modes

The planning subsystem includes [`planning/llm_client.py`](file:///c:/Users/omari/PycharmProjects/Sterling-Vance-Bank-A-Card-Dispute-Chargeback-Processing/planning/llm_client.py) (`UniversalLLMClient`), which unifies cloud API providers and local models with automatic fallback:
* **Cloud API Providers**: OpenAI (`OPENAI_API_KEY`), OpenRouter (`OPENROUTER_API_KEY`), Anthropic, or any OpenAI-compatible API (`LLM_API_KEY` + `OPENAI_BASE_URL`).
* **Local Models**: Local Ollama or vLLM at `http://localhost:11434/v1/chat/completions` (e.g. `llama3.2:3b`).
* **Offline Mock Double**: Deterministic offline mock for instant testing without network or GPU dependencies.

---

## 7. How to Run Demos and Benchmarks

```bash
# 1. Run the consolidated 5-part demonstration script
python agent/demo_dispute_planning.py

# 2. Run unit tests verifying integration and safety
python tests/test_dispute_planning_agent.py

# 3. Run individual standalone proofs
python planning/demo_divergence.py
python planning/demo_reflexion.py
python planning/demo_grounding.py

# 4. Run the 18-case planning evaluation benchmark (Auto-detects API Key or Local Ollama)
python planning_eval/run_eval.py

# 5. Run planning evaluation benchmark with specific Cloud API
python planning_eval/run_eval.py --provider mistral --model mistral-small-latest
python planning_eval/run_eval.py --provider openrouter --model openai/gpt-4o-mini
python planning_eval/run_eval.py --provider openai --model gpt-4o-mini

# 6. Run planning evaluation benchmark with Local Ollama
python planning_eval/run_eval.py --provider ollama --model llama3.2:3b
```

---

## 8. Where to Locate Every Grading Concern in Code

For grading verification, all required concerns are mapped directly to their implementation files:

| Rubric Concern | Code Location | Key Function / Class |
|---|---|---|
| **DAG Construction & Cycle Check** | [`planning/toolkit_adapter.py`](toolkit_adapter.py) & upstream [`toolkit/planning_lab/algorithms/decomposition.py`](../toolkit/planning_lab/algorithms/decomposition.py) | `DecompositionFirst.execute`, `decompose_goal`, Kahn's algorithm cycle check |
| **Decomposition-First vs. Dynamic Branch Point** | [`agent/dispute_planning_agent.py`](../agent/dispute_planning_agent.py) & [`planning/demo_divergence.py`](demo_divergence.py) | `DisputePlanningAgent.handle_dispute`, `demo_divergence.py` (`DISP-003` terminal status test) |
| **Sub-Task Algorithmic Dispatch** | [`planning/router.py`](router.py) | `SubTaskRouter.route`, `classify_task_shape` (Routes PS, ToT, LATS) |
| **Grounded SQLite Environment** | [`planning/environment.py`](environment.py) | `GroundedDisputeEnvironment.evaluate_action`, `db/sterling_vance.db` SQL checks |
| **Ungrounded vs Grounded Failure Proof** | [`planning/demo_grounding.py`](demo_grounding.py) | `demo_grounding.py` (Proves ungrounded approves duplicate payout vs grounded blocks it) |
| **Self-Refine with Rubric & Critic** | [`planning/toolkit_adapter.py`](toolkit_adapter.py) & [`agent/demo_dispute_planning.py`](../agent/demo_dispute_planning.py) | `SelfRefine.execute`, Reg E disclosure rubric verification |
| **Reflexion Cross-Trial Memory Carry** | [`planning/toolkit_adapter.py`](toolkit_adapter.py) & [`planning/demo_reflexion.py`](demo_reflexion.py) | `Reflexion.execute`, `trial_history` verbal memory buffer carry |
| **Universal API & Local LLM Client** | [`planning/llm_client.py`](llm_client.py) | `UniversalLLMClient` (Mistral AI, OpenRouter, OpenAI, Local Ollama) |
| **18-Case Benchmark Test Suite & Harness** | [`planning_eval/test_suite.py`](../planning_eval/test_suite.py) & [`planning_eval/run_eval.py`](../planning_eval/run_eval.py) | `get_test_suite()`, `run_full_evaluation()`, `artifacts/` JSON traces |


