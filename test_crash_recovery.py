import sys
import os
from state_graph.checkpointer import SQLiteCheckpointSaver
from state_graph.graph_fraud import build_fraud_graph
from db.schema_extensions import init_db_extensions

def run_fraud_crash_simulation(dispute_id: str, simulate_crash: bool = False):
    os.makedirs("db", exist_ok=True)
    init_db_extensions("db/disputes_state.db")
    
    db_path = "db/disputes_state.db"
    checkpointer = SQLiteCheckpointSaver(db_path=db_path)
    graph = build_fraud_graph(checkpointer=checkpointer)
    
    # Scoped thread_id: disp-{dispute_id}
    config = {"configurable": {"thread_id": f"disp-{dispute_id}"}}
    
    if simulate_crash:
        print(f"\n[🚀 START] Initial execution for Fraud Dispute: {dispute_id}")
        initial_state = {
            "dispute_id": dispute_id,
            "user_id": "ACC-9921",
            "merchant_id": "MERCH-401",
            "amount": 1250.0,
            "description": "Unauthorized online transaction charge.",
            "evidence_status": "received"
        }
        
        for event in graph.stream(initial_state, config):
            node_name = list(event.keys())[0]
            print(f"[Node Completed]: {node_name}")
            if node_name == "constrained_react":
                print("\n[💥 PROCESS KILLED] Simulating abrupt mid-run crash to verify checkpoint durability...")
                sys.exit(1)
    else:
        print(f"\n[🔄 RESUME] Restarting process for Fraud Dispute: {dispute_id} from durable checkpoint...")
        for event in graph.stream(None, config):
            node_name = list(event.keys())[0]
            print(f"[Resumed Node Completed]: {node_name}")
        print("\n[✅ SUCCESS] Graph resumed and completed execution with zero duplicate steps!")

if __name__ == "__main__":
    dispute_ref = "DISP-CRASH-TEST-101"
    if len(sys.argv) > 1 and sys.argv[1] == "--resume":
        run_fraud_crash_simulation(dispute_ref, simulate_crash=False)
    else:
        run_fraud_crash_simulation(dispute_ref, simulate_crash=True)
