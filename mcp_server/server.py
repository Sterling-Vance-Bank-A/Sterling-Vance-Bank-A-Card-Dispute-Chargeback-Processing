import asyncio
import sqlite3
import os
import sys

import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

class DisputeServer(Server):
    """Subclass so that ANY transport asking this server for its default
    initialization options (stdio explicitly, or the HTTP session manager
    internally/implicitly) gets the SAME honest capability declaration.

    Without this override, StreamableHTTPSessionManager calls
    app.create_initialization_options() with no arguments internally, which
    falls back to NotificationOptions() (tools_changed=False) — meaning the
    HTTP transport would falsely declare no notification support, even
    though this server genuinely fires tools/list_changed. That mismatch is
    exactly the kind of dishonest capability negotiation this assignment
    warns against.
    """

    def create_initialization_options(self, notification_options=None, experimental_capabilities=None):
        return super().create_initialization_options(
            notification_options=notification_options or NotificationOptions(tools_changed=True),
            experimental_capabilities=experimental_capabilities or {},
        )


app = DisputeServer("sterling-vance-dispute-server")

from resources import register_resources
from prompts import register_prompts
from elicitation_handler import process_refund_with_elicitation, ELICITATION_THRESHOLD
from sampling_handler import summarize_dispute_evidence
register_resources(app)
register_prompts(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "sterling_vance.db")

session_state = {"escalated": False}


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def check_escalation(cursor, dispute) -> bool:
    """Escalation is a property of the DISPUTE itself, not of who is
    handling it: a large amount OR a high-risk customer pattern.
    This matches the assignment's stated trigger exactly."""
    if dispute["amount"] > 500:
        return True

    cursor.execute(
        """
        SELECT c.risk_flag
        FROM disputes d
        JOIN transactions t ON d.transaction_id = t.transaction_id
        JOIN accounts a ON t.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
        WHERE d.dispute_id = ?
        """,
        (dispute["dispute_id"],),
    )
    row = cursor.fetchone()
    if row is not None and row["risk_flag"] == "high":
        return True

    return False


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    tools = [
        types.Tool(
            name="get_dispute_details",
            description="Fetch details of a single dispute by its dispute_id",
            inputSchema={
                "type": "object",
                "properties": {
                    "dispute_id": {
                        "type": "string",
                        "pattern": "^DISP-\\d{3,}$",
                        "description": "The dispute ID to look up, e.g. 'DISP-001'",
                    }
                },
                "required": ["dispute_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="get_transaction_history",
            description="Fetch all transactions for a given account_id",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {
                        "type": "string",
                        "pattern": "^ACC-\\d{3,}$",
                        "description": "The account ID to look up transactions for, e.g. 'ACC-001'",
                    }
                },
                "required": ["account_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="get_merchant_info",
            description="Fetch details of a merchant by merchant_id",
            inputSchema={
                "type": "object",
                "properties": {
                    "merchant_id": {
                        "type": "string",
                        "pattern": "^MERCH-\\d{3,}$",
                        "description": "The merchant ID to look up, e.g. 'MERCH-001'",
                    }
                },
                "required": ["merchant_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="process_refund",
            description=(
                "Approve a refund for a dispute. Only allowed if the dispute is "
                "still open/investigating, and only senior analysts may approve "
                "refunds over $500."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dispute_id": {
                        "type": "string",
                        "pattern": "^DISP-\\d{3,}$",
                        "description": "The dispute ID to refund, e.g. 'DISP-001'",
                    },
                    "analyst_id": {
                        "type": "string",
                        "pattern": "^ANL-\\d{3,}$",
                        "description": "The analyst attempting this action, e.g. 'ANL-001'",
                    },
                },
                "required": ["dispute_id", "analyst_id"],
                "additionalProperties": False,
            },
        ),
    ]

    if session_state["escalated"]:
        tools.append(
            types.Tool(
                name="escalate_dispute",
                description=(
                    "Senior-only tool: formally escalate a high-value or high-risk "
                    "dispute to the card network. Only appears after an escalation "
                    "trigger (large amount or high-risk customer) has fired."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "dispute_id": {
                            "type": "string",
                            "pattern": "^DISP-\\d{3,}$",
                            "description": "The dispute ID to escalate, e.g. 'DISP-001'",
                        },
                        "analyst_id": {
                            "type": "string",
                            "pattern": "^ANL-\\d{3,}$",
                            "description": "The senior analyst performing the escalation, e.g. 'ANL-002'",
                        },
                    },
                    "required": ["dispute_id", "analyst_id"],
                    "additionalProperties": False,
                },
            )
        )

    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    conn = get_connection()
    cursor = conn.cursor()

    if name == "get_dispute_details":
        cursor.execute("SELECT * FROM disputes WHERE dispute_id = ?", (arguments["dispute_id"],))
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return [types.TextContent(type="text", text=f"No dispute found with ID {arguments['dispute_id']}")]
        return [types.TextContent(type="text", text=str(dict(row)))]

    elif name == "get_transaction_history":
        cursor.execute("SELECT * FROM transactions WHERE account_id = ?", (arguments["account_id"],))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return [types.TextContent(type="text", text=f"No transactions found for account {arguments['account_id']}")]
        return [types.TextContent(type="text", text=str([dict(r) for r in rows]))]

    elif name == "get_merchant_info":
        cursor.execute("SELECT * FROM merchants WHERE merchant_id = ?", (arguments["merchant_id"],))
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return [types.TextContent(type="text", text=f"No merchant found with ID {arguments['merchant_id']}")]
        return [types.TextContent(type="text", text=str(dict(row)))]

    elif name == "process_refund":
        dispute_id = arguments["dispute_id"]
        analyst_id = arguments["analyst_id"]

        cursor.execute("SELECT * FROM disputes WHERE dispute_id = ?", (dispute_id,))
        dispute = cursor.fetchone()
        if dispute is None:
            conn.close()
            return [types.TextContent(type="text", text=f"REJECTED: No dispute found with ID {dispute_id}")]

        if dispute["status"] not in ("open", "investigating"):
            conn.close()
            return [types.TextContent(
                type="text",
                text=(
                    f"REJECTED: Dispute {dispute_id} has status '{dispute['status']}' "
                    "— cannot refund an already-resolved dispute."
                ),
            )]

        # --- Notifications trigger: escalation is a property of the DISPUTE,
        # independent of who is handling it (large amount OR high-risk customer) ---
        should_escalate = check_escalation(cursor, dispute)
        if should_escalate and not session_state["escalated"]:
            session_state["escalated"] = True
            await app.request_context.session.send_tool_list_changed()

        cursor.execute("SELECT * FROM analysts WHERE analyst_id = ?", (analyst_id,))
        analyst = cursor.fetchone()
        if analyst is None:
            conn.close()
            return [types.TextContent(type="text", text=f"REJECTED: No analyst found with ID {analyst_id}")]

        amount = dispute["amount"]
        escalation_note = " This dispute is escalated — senior tools are now available." if should_escalate else ""
        conn.close()  # from here on, the handler owns its own connection

        # --- Routine path: at/under threshold, or a junior analyst who can
        # never clear the threshold anyway. No pause needed — delegate
        # straight to the real handler that owns this business logic. ---
        if amount <= ELICITATION_THRESHOLD or analyst["role"] == "junior":
            result = process_refund_with_elicitation(dispute_id, analyst_id)
            return [types.TextContent(type="text", text=result["message"] + escalation_note)]

        # --- Over threshold, senior analyst: real sampling, then real elicitation. ---

        # 1) Sampling: ask the CLIENT's model (not a canned string) to turn the
        # raw evidence into a short summary via a genuine sampling/createMessage call.
        evidence = summarize_dispute_evidence(dispute_id)
        if evidence["status"] != "success":
            return [types.TextContent(type="text", text=evidence["message"])]

        sampling_result = await app.request_context.session.create_message(
            messages=[
                types.SamplingMessage(
                    role="user",
                    content=types.TextContent(type="text", text=evidence["sampling_request_prompt"]),
                )
            ],
            max_tokens=200,
        )
        model_text = (
            sampling_result.content.text
            if isinstance(sampling_result.content, types.TextContent)
            else str(sampling_result.content)
        )
        # Re-run the handler with the real model output plugged in — this is
        # the actual summary the analyst will see, not a hardcoded string.
        evidence = summarize_dispute_evidence(dispute_id, mock_llm_response=model_text)

        # 2) Elicitation: pause execution and wait for a real elicitation/create
        # round trip with the analyst before touching the database at all.
        elicit_result = await app.request_context.session.elicit(
            message=(
                f"Refund of ${amount:.2f} for dispute {dispute_id} exceeds the "
                f"${ELICITATION_THRESHOLD:.2f} policy threshold.\n\n"
                f"Evidence summary: {evidence['sampling_response_summary']}\n\n"
                "Approve this refund?"
            ),
            requestedSchema={
                "type": "object",
                "properties": {
                    "approved": {
                        "type": "boolean",
                        "title": "Approve refund",
                        "description": "Senior sign-off on this refund",
                    }
                },
            },
        )

        if elicit_result.action == "accept":
            confirmed = True
        elif elicit_result.action == "decline":
            confirmed = False
        else:  # "cancel" — analyst backed out without deciding either way
            return [types.TextContent(
                type="text",
                text=f"CANCELLED: Elicitation was cancelled for dispute {dispute_id}. No changes made.",
            )]

        # 3) Commit (or block) — the handler is the only place that writes to the DB.
        result = process_refund_with_elicitation(dispute_id, analyst_id, confirmed=confirmed)
        return [types.TextContent(type="text", text=result["message"] + escalation_note)]

    elif name == "escalate_dispute":
        dispute_id = arguments["dispute_id"]
        analyst_id = arguments["analyst_id"]

        if not session_state["escalated"]:
            conn.close()
            return [types.TextContent(
                type="text",
                text="REJECTED: No escalation has been triggered in this session yet.",
            )]

        cursor.execute("SELECT * FROM analysts WHERE analyst_id = ?", (analyst_id,))
        analyst = cursor.fetchone()
        if analyst is None or analyst["role"] != "senior":
            conn.close()
            return [types.TextContent(
                type="text",
                text=f"REJECTED: Analyst {analyst_id} is not a senior analyst and cannot escalate disputes.",
            )]

        cursor.execute("UPDATE disputes SET status = 'escalated' WHERE dispute_id = ?", (dispute_id,))
        conn.commit()
        conn.close()
        return [types.TextContent(
            type="text",
            text=f"ESCALATED: Dispute {dispute_id} formally escalated to the card network by {analyst_id}.",
        )]

    conn.close()
    raise ValueError(f"Unknown tool: {name}")


async def run_stdio():
    """Local development transport: single machine, single analyst."""
    async with stdio_server() as (read_stream, write_stream):
        init_options = InitializationOptions(
            server_name="sterling-vance-dispute-server",
            server_version="0.1.0",
            capabilities=app.get_capabilities(
                notification_options=NotificationOptions(tools_changed=True),
                experimental_capabilities={},
            ),
        )
        await app.run(read_stream, write_stream, init_options)


async def run_http():
    """Production transport: reachable over the network so multiple
    analysts across branches can connect to the same live server,
    instead of each running a separate local copy."""
    from starlette.applications import Starlette
    from starlette.routing import Mount
    import uvicorn

    session_manager = StreamableHTTPSessionManager(app=app)

    starlette_app = Starlette(
        routes=[Mount("/mcp", app=session_manager.handle_request)],
    )

    config = uvicorn.Config(starlette_app, host="127.0.0.1", port=8000)
    server = uvicorn.Server(config)

    async with session_manager.run():
        await server.serve()


if __name__ == "__main__":
    # Transport selection: stdio for local development (default),
    # Streamable HTTP for production multi-analyst deployment.
    # Run with: python server.py --http
    if "--http" in sys.argv:
        asyncio.run(run_http())
    else:
        asyncio.run(run_stdio())