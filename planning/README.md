# Person B — Planning & Search

This package is the **Person B** contribution for the Sterling Vance Bank Card Dispute & Chargeback project.

## Scope

Person B owns:

1. Plan-and-Solve adaptation.
2. Tree-of-Thoughts adaptation and bounded beam search.
3. LATS/MCTS adaptation with grounded external feedback.
4. Sub-task routing.
5. The 15-case PS/ToT/Ungrounded-LATS/Grounded-LATS benchmark.

The course guide assigns these responsibilities to Person B and requires routing linear, combinatorial, and high-stakes dispute sub-tasks to the matching planning method.  fileciteturn1file0L5-L10

## Reference toolkit basis

The required reference repository is:

https://github.com/AmrSheta22/task_decomposition_and_planning

The upstream repository currently exposes focused modules for Plan-and-Solve, Tree-of-Thoughts, LATS, and a swappable `Environment` feedback seam. Its README also describes bounded ToT, LATS with external feedback, and JSON traces under `artifacts/`. citeturn604346view0

The implementations here preserve that separation of concerns while adapting the interfaces to Sterling Vance's existing class-based router and SQLite dispute database. The upstream Plan-and-Solve implementation uses a single explicit PLAN/SOLUTION call; the upstream ToT implementation generates, evaluates, and prunes candidates with a beam; the upstream LATS implementation uses UCT, expansion, external environment feedback, branch reflection, and backpropagation. citeturn245359view0turn245359view1turn245359view2

## Routing policy

| Sub-task shape | Method |
|---|---|
| Evidence aggregation, dispute timeline, fee/exposure calculation, customer notification | Plan-and-Solve |
| Ranking recovery priority, filing urgency, merchant/dispute risk | Tree-of-Thoughts |
| Refunds, network escalation, database state mutation | Grounded LATS |

The routing rules are implemented in `planning/router.py`.

## Grounded LATS

The reference toolkit's default environment is intentionally randomized. The course assignment explicitly requires replacing that evaluator with a real feedback source. The project implementation uses `db/sterling_vance.db` in **read-only** mode to validate dispute status, refund eligibility, analyst role, and senior-analyst requirements. citeturn245359view3

No database write is performed by the environment validator.

## Benchmark

Run from repository root:

```bash
python -m planning.benchmark
```

This creates:

- `artifacts/person_b_15_case_benchmark.json`
- `artifacts/person_b_comparison_table.md`
- one JSON trace per case/method under `artifacts/`

The fixed suite contains 15 banking cases: 5 linear, 5 ranking, and 5 high-stakes. The benchmark measures success, LLM calls, tokens, latency, and estimated cost. The local benchmark uses a deterministic model double so it can run without API credits; final quality numbers should be regenerated with the team's live model adapter before being presented as production results.

The 15-case requirement and the requested comparison of Plan-and-Solve, Tree-of-Thoughts, ungrounded LATS, and grounded LATS come from the Person B guide. fileciteturn1file0L115-L135

## GitHub note

This folder is the code contribution to place into the team's shared repository. The actual GitHub **fork history, issues, pull requests, linked commits, and final live-model benchmark** must be created in the team's GitHub repository; they cannot be fabricated inside a ZIP archive.
