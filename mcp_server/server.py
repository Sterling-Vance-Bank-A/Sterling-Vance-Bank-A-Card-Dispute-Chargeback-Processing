import asyncio
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

app = Server("sterling-vance-dispute-server")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_dispute_details",
            description="Fetch details of a single dispute by its ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "dispute_id": {
                        "type": "integer",
                        "description": "The ID of the dispute to look up",
                    }
                },
                "required": ["dispute_id"],
                "additionalProperties": False,
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_dispute_details":
        return [types.TextContent(type="text", text=f"[placeholder] dispute {arguments['dispute_id']}")]
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