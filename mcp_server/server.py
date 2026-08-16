import asyncio
import sqlite3
import os
import sys

import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from elicitation_handler import process_refund_with_elicitation
from sampling_handler import summarize_dispute_evidence


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


# ---------------------------------------------------------------------------
# Tool registry — built once, mutated when escalation fires
# ---------------------------------------------------------------------------

def _build_base_tools() -> list[types.Tool]:
    return [
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
                    "confirmed": {
                        "type": "boolean",
                        "description": "Optional explicit human confirmation flag for high-value refunds",
                    },
                },
                "required": ["dispute_id", "analyst_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="scan_repeat_dispute_patterns",
            description="Scans a customer's transaction history against a specific merchant to detect repeat-dispute patterns. This is a long-running operation that sends progress updates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "pattern": "^CUST-\\d{3,}$",
                        "description": "The customer ID to scan, e.g. 'CUST-073'",
                    },
                    "merchant_id": {
                        "type": "string",
                        "pattern": "^MERCH-\\d{3,}$",
                        "description": "The merchant ID to check against, e.g. 'MERCH-006'",
                    },
                },
                "required": ["customer_id", "merchant_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="summarize_dispute_evidence",
            description="Fetches raw dispute evidence and uses sampling to create a human-readable summary.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dispute_id": {
                        "type": "string",
                        "pattern": "^DISP-\\d{3,}$",
                        "description": "The dispute ID to summarize, e.g. 'DISP-001'",
                    }
                },
                "required": ["dispute_id"],
                "additionalProperties": False,
            },
        ),
    ]


# ---------------------------------------------------------------------------
# list_tools handler
# ---------------------------------------------------------------------------

async def handle_list_tools(ctx, params) -> types.ListToolsResult:
    tools = _build_base_tools()

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

    return types.ListToolsResult(tools=tools)


# ---------------------------------------------------------------------------
# call_tool handler
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Server-side argument validation helpers
# ---------------------------------------------------------------------------

import re as _re

_DISP_RE  = _re.compile(r"^DISP-\d{3,}$")
_ANL_RE   = _re.compile(r"^ANL-\d{3,}$")
_MERCH_RE = _re.compile(r"^MERCH-\d{3,}$")
_ACC_RE   = _re.compile(r"^ACC-\d{3,}$")
_CUST_RE  = _re.compile(r"^CUST-\d{3,}$")


def _bad(msg: str) -> types.CallToolResult:
    """Return a user-visible validation error without touching the database."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=f"VALIDATION ERROR: {msg}")]
    )


def _validate_dispute_id(val) -> str | None:
    if not isinstance(val, str) or not _DISP_RE.match(val):
        return f"dispute_id '{val}' must match DISP-<3+ digits> (e.g. DISP-001)"
    return None


def _validate_analyst_id(val) -> str | None:
    if not isinstance(val, str) or not _ANL_RE.match(val):
        return f"analyst_id '{val}' must match ANL-<3+ digits> (e.g. ANL-001)"
    return None


def _validate_merchant_id(val) -> str | None:
    if not isinstance(val, str) or not _MERCH_RE.match(val):
        return f"merchant_id '{val}' must match MERCH-<3+ digits> (e.g. MERCH-001)"
    return None


def _validate_account_id(val) -> str | None:
    if not isinstance(val, str) or not _ACC_RE.match(val):
        return f"account_id '{val}' must match ACC-<3+ digits> (e.g. ACC-001)"
    return None


def _validate_customer_id(val) -> str | None:
    if not isinstance(val, str) or not _CUST_RE.match(val):
        return f"customer_id '{val}' must match CUST-<3+ digits> (e.g. CUST-001)"
    return None


# ---------------------------------------------------------------------------
# call_tool handler  (explicit server-side validation before every DB action)
# ---------------------------------------------------------------------------

async def handle_call_tool(ctx, params) -> types.CallToolResult:
    name = params.name
    arguments = dict(params.arguments) if params.arguments else {}

    # ── get_dispute_details ──────────────────────────────────────────────────
    if name == "get_dispute_details":
        # 1. Format validation
        err = _validate_dispute_id(arguments.get("dispute_id"))
        if err:
            return _bad(err)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM disputes WHERE dispute_id = ?", (arguments["dispute_id"],))
        row = cursor.fetchone()
        conn.close()
        # 2. Existence check
        if row is None:
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No dispute found with ID {arguments['dispute_id']}")])
        return types.CallToolResult(content=[types.TextContent(type="text", text=str(dict(row)))])

    # ── get_transaction_history ──────────────────────────────────────────────
    elif name == "get_transaction_history":
        # 1. Format validation
        err = _validate_account_id(arguments.get("account_id"))
        if err:
            return _bad(err)

        conn = get_connection()
        cursor = conn.cursor()
        # 2. Existence check — verify account exists
        cursor.execute("SELECT account_id FROM accounts WHERE account_id = ?", (arguments["account_id"],))
        if cursor.fetchone() is None:
            conn.close()
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No account found with ID {arguments['account_id']}")])
        cursor.execute("SELECT * FROM transactions WHERE account_id = ?", (arguments["account_id"],))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No transactions found for account {arguments['account_id']}")])
        return types.CallToolResult(content=[types.TextContent(type="text", text=str([dict(r) for r in rows]))])

    # ── get_merchant_info ────────────────────────────────────────────────────
    elif name == "get_merchant_info":
        # 1. Format validation
        err = _validate_merchant_id(arguments.get("merchant_id"))
        if err:
            return _bad(err)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM merchants WHERE merchant_id = ?", (arguments["merchant_id"],))
        row = cursor.fetchone()
        conn.close()
        # 2. Existence check
        if row is None:
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No merchant found with ID {arguments['merchant_id']}")])
        return types.CallToolResult(content=[types.TextContent(type="text", text=str(dict(row)))])

    # ── scan_repeat_dispute_patterns ─────────────────────────────────────────
    elif name == "scan_repeat_dispute_patterns":
        # 1. Format validation
        err = _validate_customer_id(arguments.get("customer_id"))
        if err:
            return _bad(err)
        err = _validate_merchant_id(arguments.get("merchant_id"))
        if err:
            return _bad(err)

        customer_id = arguments["customer_id"]
        merchant_id = arguments["merchant_id"]

        conn = get_connection()
        cursor = conn.cursor()

        # 2. Existence checks — customer and merchant must exist
        cursor.execute(
            "SELECT customer_id FROM customers WHERE customer_id = ?", (customer_id,)
        )
        if cursor.fetchone() is None:
            conn.close()
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No customer found with ID {customer_id}")])

        cursor.execute(
            "SELECT merchant_id FROM merchants WHERE merchant_id = ?", (merchant_id,)
        )
        if cursor.fetchone() is None:
            conn.close()
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No merchant found with ID {merchant_id}")])

        cursor.execute(
            """
            SELECT t.transaction_id, t.merchant_id
            FROM transactions t
            JOIN accounts a ON t.account_id = a.account_id
            WHERE a.customer_id = ?
            """,
            (customer_id,)
        )
        transactions = cursor.fetchall()

        total_txns = len(transactions)
        matched_txns = []

        for i, txn in enumerate(transactions, 1):
            if txn["merchant_id"] == merchant_id:
                matched_txns.append(txn["transaction_id"])

            meta = ctx.meta
            progress_token = None
            if meta:
                if isinstance(meta, dict):
                    progress_token = meta.get("progressToken") or meta.get("progress_token")
                else:
                    progress_token = getattr(meta, "progressToken", None) or getattr(meta, "progress_token", None)

            if progress_token is not None and ctx is not None and hasattr(ctx, "session") and ctx.session is not None:
                await ctx.session.send_progress_notification(
                    progress_token=progress_token,
                    progress=i + 1,
                    total=total_txns,
                )

            await asyncio.sleep(0.01)

        conn.close()
        pattern_detected = len(matched_txns) >= 3

        result_str = (
            f"Scanned {total_txns} transactions for customer {customer_id}. "
            f"Found {len(matched_txns)} transaction(s) with merchant {merchant_id}: {matched_txns}. "
            f"Repeat-dispute pattern detected: {pattern_detected}."
        )
        return types.CallToolResult(content=[types.TextContent(type="text", text=result_str)])

    # ── summarize_dispute_evidence ───────────────────────────────────────────
    elif name == "summarize_dispute_evidence":
        # 1. Format validation
        err = _validate_dispute_id(arguments.get("dispute_id"))
        if err:
            return _bad(err)

        dispute_id = arguments["dispute_id"]

        # 2. Existence check — dispute must exist before sampling is invoked
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT dispute_id FROM disputes WHERE dispute_id = ?", (dispute_id,))
        if cursor.fetchone() is None:
            conn.close()
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No dispute found with ID {dispute_id}")])
        conn.close()

        res = summarize_dispute_evidence(dispute_id)
        if res["status"] == "error":
            return types.CallToolResult(content=[types.TextContent(type="text", text=res["message"])])

        return types.CallToolResult(content=[types.TextContent(type="text", text=res["sampling_response_summary"])])

    # ── process_refund ───────────────────────────────────────────────────────
    elif name == "process_refund":
        # 1. Format validation
        err = _validate_dispute_id(arguments.get("dispute_id"))
        if err:
            return _bad(err)
        err = _validate_analyst_id(arguments.get("analyst_id"))
        if err:
            return _bad(err)

        dispute_id = arguments["dispute_id"]
        analyst_id = arguments["analyst_id"]
        confirmed  = arguments.get("confirmed")

        conn = get_connection()
        cursor = conn.cursor()

        # 2. Existence checks — both dispute and analyst must exist
        cursor.execute("SELECT dispute_id FROM disputes WHERE dispute_id = ?", (dispute_id,))
        if cursor.fetchone() is None:
            conn.close()
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No dispute found with ID {dispute_id}")])

        cursor.execute("SELECT analyst_id FROM analysts WHERE analyst_id = ?", (analyst_id,))
        if cursor.fetchone() is None:
            conn.close()
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No analyst found with ID {analyst_id}")])

        # 3. Bounds / state check — fire escalation notification if needed
        cursor.execute("SELECT * FROM disputes WHERE dispute_id = ?", (dispute_id,))
        dispute = cursor.fetchone()
        if dispute:
            should_escalate = check_escalation(cursor, dispute)
            if should_escalate and not session_state["escalated"]:
                session_state["escalated"] = True
                if ctx is not None and hasattr(ctx, "session") and ctx.session is not None:
                    await ctx.session.send_tool_list_changed()

        conn.close()

        res = process_refund_with_elicitation(dispute_id, analyst_id, confirmed)
        return types.CallToolResult(content=[types.TextContent(type="text", text=res["message"])])

    # ── escalate_dispute ─────────────────────────────────────────────────────
    elif name == "escalate_dispute":
        # 1. Format validation
        err = _validate_dispute_id(arguments.get("dispute_id"))
        if err:
            return _bad(err)
        err = _validate_analyst_id(arguments.get("analyst_id"))
        if err:
            return _bad(err)

        dispute_id = arguments["dispute_id"]
        analyst_id = arguments["analyst_id"]

        # 2. State check — escalation must have been triggered this session
        if not session_state["escalated"]:
            return types.CallToolResult(content=[types.TextContent(
                type="text",
                text="REJECTED: No escalation has been triggered in this session yet.",
            )])

        conn = get_connection()
        cursor = conn.cursor()

        # 3. Existence check — dispute must exist
        cursor.execute("SELECT dispute_id FROM disputes WHERE dispute_id = ?", (dispute_id,))
        if cursor.fetchone() is None:
            conn.close()
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"No dispute found with ID {dispute_id}")])

        # 4. Role check — analyst must exist and be senior
        cursor.execute("SELECT * FROM analysts WHERE analyst_id = ?", (analyst_id,))
        analyst = cursor.fetchone()
        if analyst is None or analyst["role"] != "senior":
            conn.close()
            return types.CallToolResult(content=[types.TextContent(
                type="text",
                text=f"REJECTED: Analyst {analyst_id} is not a senior analyst and cannot escalate disputes.",
            )])

        # 5. Allowed-state check — dispute must be in an escalatable state
        cursor.execute("SELECT status FROM disputes WHERE dispute_id = ?", (dispute_id,))
        disp_row = cursor.fetchone()
        if disp_row and disp_row["status"] in ("refunded", "escalated", "denied"):
            conn.close()
            return types.CallToolResult(content=[types.TextContent(
                type="text",
                text=f"REJECTED: Dispute {dispute_id} is already in terminal status '{disp_row['status']}' and cannot be escalated.",
            )])

        cursor.execute("UPDATE disputes SET status = 'escalated' WHERE dispute_id = ?", (dispute_id,))
        conn.commit()
        conn.close()
        return types.CallToolResult(content=[types.TextContent(
            type="text",
            text=f"ESCALATED: Dispute {dispute_id} formally escalated to the card network by {analyst_id}.",
        )])

    raise ValueError(f"Unknown tool: {name}")


def _register(method_name, req_type, handler):
    if hasattr(app, "add_request_handler"):
        app.add_request_handler(method_name, req_type, handler)
    elif hasattr(app, "_request_handlers"):
        app._request_handlers[req_type] = handler
    elif hasattr(app, "request_handlers"):
        app.request_handlers[req_type] = handler

_register("tools/list", types.ListToolsRequest, handle_list_tools)
_register("tools/call", types.CallToolRequestParams, handle_call_tool)


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