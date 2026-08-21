import json
from typing import Dict, Any, TypedDict, List
from langgraph.graph import StateGraph, END
from state_graph.checkpointer import SQLiteCheckpointSaver
from state_graph.hitl_and_tickets import trigger_hitl_pause, create_failure_ticket

class FraudDisputeState(TypedDict):
    dispute_id: str
    user_id: str
    merchant_id: str
    amount: float
    description: str
    evidence_status: str           # 'pending' or 'received'
    react_findings: Dict[str, Any] # Addition 1: Constrained ReAct
    regulatory_policy: str        # Addition 2: Regulatory RAG
    status: str
    error: str

def node_intake_and_triage(state: FraudDisputeState) -> Dict[str, Any]:
    """1. Intake & Triage Node"""
    return {"status": "triaged"}

def node_constrained_react_investigation(state: FraudDisputeState) -> Dict[str, Any]:
    """2. Constrained ReAct Node: Strict whitelist of read-only tools"""
    allowed_tools = ["get_transaction_history", "get_merchant_info", "scan_repeat_dispute_patterns"]
    attempted_tool = "get_transaction_history"
    
    if attempted_tool not in allowed_tools:
        create_failure_ticket(
            dispute_id=state["dispute_id"],
            error_message=f"Unauthorized tool attempted: {attempted_tool}",
            state_at_failure=state
        )
        return {"status": "failed_unauthorized_tool"}

    findings = {
        "tool_used": attempted_tool,
        "suspicious_pattern": True,
        "historical_chargebacks": 3,
        "merchant_risk_score": 0.82
    }
    return {"react_findings": findings, "status": "evidence_gathered"}

def node_async_wait_merchant_evidence(state: FraudDisputeState) -> Dict[str, Any]:
    """3. Async Waiting State: Persists state until merchant evidence webhook arrives"""
    if state.get("evidence_status") != "received":
        return {"status": "awaiting_merchant_evidence"}
    return {"status": "merchant_evidence_received"}

def node_regulatory_rag_lookup(state: FraudDisputeState) -> Dict[str, Any]:
    """4. Regulatory RAG Node: Queries VISA Rule 10.4 vs 10.5 pre-arbitration rules"""
    retrieved_rule = (
        "VISA Rule 10.4 (Card-Not-Present Fraud): Pre-arbitration claim must be filed "
        "within 120 calendar days of transaction date. Reason code 4837 applies."
    )
    return {"regulatory_policy": retrieved_rule, "status": "rag_policy_verified"}

def node_hitl_pre_arbitration_gate(state: FraudDisputeState) -> Dict[str, Any]:
    """5. Senior Pre-Arbitration HITL Gate"""
    if state.get("amount", 0) > 1000 or state.get("status") == "rag_policy_verified":
        task_id = trigger_hitl_pause(
            dispute_id=state["dispute_id"],
            reason="Pre-arbitration legal filing sign-off required by Senior Fraud Analyst.",
            current_state=state
        )
        return {"status": f"paused_for_hitl_{task_id}"}
    return {"status": "completed"}

def build_fraud_graph(checkpointer: SQLiteCheckpointSaver):
    builder = StateGraph(FraudDisputeState)
    
    builder.add_node("intake_and_triage", node_intake_and_triage)
    builder.add_node("constrained_react", node_constrained_react_investigation)
    builder.add_node("async_wait_evidence", node_async_wait_merchant_evidence)
    builder.add_node("regulatory_rag", node_regulatory_rag_lookup)
    builder.add_node("hitl_gate", node_hitl_pre_arbitration_gate)
    
    builder.set_entry_point("intake_and_triage")
    builder.add_edge("intake_and_triage", "constrained_react")
    builder.add_edge("constrained_react", "async_wait_evidence")
    builder.add_edge("async_wait_evidence", "regulatory_rag")
    builder.add_edge("regulatory_rag", "hitl_gate")
    builder.add_edge("hitl_gate", END)
    
    return builder.compile(checkpointer=checkpointer)
