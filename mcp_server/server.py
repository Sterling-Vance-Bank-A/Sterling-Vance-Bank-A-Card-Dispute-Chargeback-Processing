import asyncio
import sqlite3
import os

import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

app = Server("sterling-vance-dispute-server")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "sterling_vance.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_dispute_details",
            description="Fetch details of a single dispute by its dispute_id",
            inputSchema={
                "type": "object",
                "properties": {
                    "dispute_id": {
                        "type": "string",
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
                        "description": "The account ID to look up transactions for",
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
                        "description": "The merchant ID to look up",
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
                        "description": "The dispute ID to refund, e.g. 'DISP-001'",
                    },
                    "analyst_id": {
                        "type": "string",
                        "description": "The analyst attempting this action, e.g. 'ANL-001'",
                    },
                },
                "required": ["dispute_id", "analyst_id"],
                "additionalProperties": False,
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    conn = get_connection()
    cursor = conn.cursor()

    if name == "get_dispute_details":
        cursor.execute(
            "SELECT * FROM disputes WHERE dispute_id = ?",
            (arguments["dispute_id"],),
        )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return [types.TextContent(type="text", text=f"No dispute found with ID {arguments['dispute_id']}")]
        return [types.TextContent(type="text", text=str(dict(row)))]

    elif name == "get_transaction_history":
        cursor.execute(
            "SELECT * FROM transactions WHERE account_id = ?",
            (arguments["account_id"],),
        )
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return [types.TextContent(type="text", text=f"No transactions found for account {arguments['account_id']}")]
        return [types.TextContent(type="text", text=str([dict(r) for r in rows]))]

    elif name == "get_merchant_info":
        cursor.execute(
            "SELECT * FROM merchants WHERE merchant_id = ?",
            (arguments["merchant_id"],),
        )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return [types.TextContent(type="text", text=f"No merchant found with ID {arguments['merchant_id']}")]
        return [types.TextContent(type="text", text=str(dict(row)))]

    elif name == "process_refund":
        dispute_id = arguments["dispute_id"]
        analyst_id = arguments["analyst_id"]

        # --- Layer 2: Business validation (beyond schema) ---
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

        # --- Layer 3: Authorization check (in the handler, not the schema) ---
        cursor.execute("SELECT * FROM analysts WHERE analyst_id = ?", (analyst_id,))
        analyst = cursor.fetchone()
        if analyst is None:
            conn.close()
            return [types.TextContent(type="text", text=f"REJECTED: No analyst found with ID {analyst_id}")]

        REFUND_THRESHOLD = 500.0
        if analyst["role"] == "junior" and dispute["amount"] > REFUND_THRESHOLD:
            conn.close()
            return [types.TextContent(
                type="text",
                text=(
                    f"REJECTED: Analyst {analyst_id} is junior and not authorized to "
                    f"approve a refund of ${dispute['amount']} (over ${REFUND_THRESHOLD} "
                    "threshold). Requires senior analyst."
                ),
            )]

        # --- All checks passed: perform the refund ---
        cursor.execute(
            "UPDATE disputes SET status = 'refunded', resolved_at = datetime('now') WHERE dispute_id = ?",
            (dispute_id,),
        )
        conn.commit()
        conn.close()
        return [types.TextContent(
            type="text",
            text=f"APPROVED: Dispute {dispute_id} (${dispute['amount']}) refunded by analyst {analyst_id}.",
        )]

    conn.close()
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        # Capability declaration — honest and explicit.
        # tools_changed=True because we genuinely push
        # notifications/tools/list_changed later in this project.
        # elicitation, sampling, resources, and prompts are NOT declared
        # here because they are not implemented in this server session yet.
        init_options = InitializationOptions(
            server_name="sterling-vance-dispute-server",
            server_version="0.1.0",
            capabilities=app.get_capabilities(
                notification_options=NotificationOptions(
                    tools_changed=True,
                ),
                experimental_capabilities={},
            ),
        )
        await app.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())