# Memory Module — Sterling Vance Bank

## The Problem
Dispute analysts review multi-session $500+ fraud disputes. Without memory, analysts re-explain context every session. Forgetting escalation status or prior merchant findings leads to duplicate escalations or regulatory compliance violations.

## Architecture

| Subsystem | File | Storage / Backing | Eviction / Retention Policy |
|---|---|---|---|
| **Short-Term Buffer** | `short_term.py` | `collections.deque(maxlen=20)` | Prunes oldest on turn 21; triggers Promote-or-Drop router |
| **Scratchpad** | `short_term.py` | Dict-backed working memory | **Never pruned or touched by buffer clearance** |
| **Episodic Store** | `episodic_store.py` | SQLite (`episodes` table in `db/memory.db`) | Append-only per-session interaction and evidence log |
| **Semantic Store** | `semantic_store.py` | SQLite (`semantic_facts` table in `db/memory.db`) | Versioned facts (`version`, `valid_from`, `deprecated_at`, `status`) |
| **Promote-or-Drop Router** | `router.py` | `PromoteOrDropRouter` (threshold=0.4) | Routes buffer overflow to **FORGET** or **EPISODIC** (never semantic) |
| **Consolidation Engine** | `consolidation.py` | `ConsolidationEngine` | Periodic background pass over episodic store to update semantic facts |

## Real Conflict Resolved

### Entity: Merchant `MERCH-004` (Attribute: `risk_score`)
* **Episode A (Day 1)**: `"MERCH-004 risk_score = 45 as of initial onboarding assessment"`
  * **Result**: Fact inserted as `version=1`, `status='deprecated'`, `deprecated_at` recorded.
* **Episode B (Day 3)**: `"MERCH-004 risk_score = 92 following fraud investigation completed"`
  * **Result**: Fact inserted as `version=2`, `status='active'`, `conflict_note='Conflict resolution: newer_value_wins'`.
* **Resolution Policy**: `newer_value_wins` — historical fact is preserved with version audit history, never silently overwritten.

## Router Audit Trail
All promote-or-drop decisions are logged with timestamp, session, turn, score, decision (`PROMOTE` or `FORGET`), and snippet:
* **Log Location**: [`memory/router_decisions.log`](file:///c:/Users/omari/PycharmProjects/Sterling-Vance-Bank-A-Card-Dispute-Chargeback-Processing/memory/router_decisions.log)
* **Scoring Factors**: Recency (0.3), Entity Tags (`dispute_id`, `analyst_id`, `fraud_flag`, `amount`) (0.4), Content Keywords (`disp-`, `fraud`, `escalat`, `risk`, `refund`) (0.3).

## Where to Find Each Concern
* **Routing Decision Code**: `router.py` `PromoteOrDropRouter.route()`
* **Consolidation Trigger**: `consolidation.py` `ConsolidationEngine.run_consolidation_pass()`
* **Conflict Resolution & Expiration**: `consolidation.py` + `semantic_store.py` `upsert_fact()` & `expire_old_facts()`
* **Scratchpad Protection**: `short_term.py` `Scratchpad` class (tested: survives `buffer.clear()`)

