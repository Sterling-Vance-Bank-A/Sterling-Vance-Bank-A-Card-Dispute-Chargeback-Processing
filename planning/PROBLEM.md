# Planning Problem: Dispute Resolution Decisioning

## The Real Request

A Sterling Vance dispute analyst opens a new case (e.g. "$1,200 charge, customer claims
fraud, merchant MERCH-XXX has 3 prior chargebacks, account risk score 92") and has to decide,
right now, how to resolve it: which reason code applies, what evidence needs to be pulled,
whether the amount and dispute status permit a refund or require escalation to a senior
analyst, and what the recommended action is (provisional credit, deny, escalate to network).

This is not a single lookup. It requires: pulling transaction/merchant history, checking
policy eligibility (via the existing RAG subsystem), applying business rules (analyst
seniority thresholds, dispute status constraints), and deciding an action — in an order that
can change based on what earlier steps find (e.g. if the merchant record is missing, or the
dispute is already in a terminal status, the rest of the plan has to change).

## Who Sends This Request Today

Every dispute analyst, on every new case that crosses the $500 elicitation threshold or
involves a compound reason (fraud + prior chargeback pattern). Today this is done by hand:
an analyst manually chains policy lookup, risk check, and escalation rule before deciding.

## The Real Cost of a Wrong Plan

- Approving a refund on a dispute already in `denied`/`refunded` status is a duplicate-payout error.
- Escalating or refunding a $500+ case without senior analyst sign-off breaches Sterling
  Vance's own compliance/elicitation requirement (documented in `mcp_server/elicitation_handler.py`).
- A wrong reason-code classification produces an indefensible chargeback response to the card
  network, risking real financial loss.

This mirrors the same "forgetting costs real money" stakes cited in the Memory & RAG Lab
README, but on the decisioning side, not the retrieval side.

## Ownership: A Separate Agent From `memory_agent.py`

This work is owned by a new **Dispute Planning Agent**
(`agent/dispute_planning_agent.py`), which is distinct from and does not modify
`agent/memory_agent.py`. The memory/RAG agent answers policy questions and remembers
session state; the planning agent decomposes and resolves an incoming dispute end-to-end.
Both agents reuse the same `mcp_server/` and `db/sterling_vance.db` unchanged.
