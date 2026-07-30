import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    url = "http://127.0.0.1:8000/mcp"

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            result = await session.initialize()
            print("=== Connected over Streamable HTTP ===")
            print("Server capabilities:", result.capabilities)

            print()
            print("=== Available tools ===")
            tools = await session.list_tools()
            for tool in tools.tools:
                print("-", tool.name)

            print()
            print("=== get_dispute_details(DISP-001) over HTTP ===")
            call_result = await session.call_tool(
                "get_dispute_details", {"dispute_id": "DISP-001"}
            )
            for content in call_result.content:
                print(content.text)


if __name__ == "__main__":
    asyncio.run(main())