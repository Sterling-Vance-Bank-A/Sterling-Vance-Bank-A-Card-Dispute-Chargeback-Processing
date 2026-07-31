import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_server/server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            result = await session.initialize()
            print("=== Server capabilities ===")
            print(result.capabilities)

            print()
            print("=== Available tools ===")
            tools = await session.list_tools()
            for tool in tools.tools:
                print("-", tool.name)

            print()
            print("=== get_dispute_details(DISP-001) ===")
            call_result = await session.call_tool("get_dispute_details", {"dispute_id": "DISP-001"})
            for content in call_result.content:
                print(content.text)

            print()
            print("=== get_transaction_history(ACC-001) ===")
            call_result = await session.call_tool("get_transaction_history", {"account_id": "ACC-001"})
            for content in call_result.content:
                print(content.text)

            print()
            print("=== get_merchant_info(MERCH-001) ===")
            call_result = await session.call_tool("get_merchant_info", {"merchant_id": "MERCH-001"})
            for content in call_result.content:
                print(content.text)

            print()
            print("=== get_merchant_info(MERCH-999) — should not be found ===")
            call_result = await session.call_tool("get_merchant_info", {"merchant_id": "MERCH-999"})
            for content in call_result.content:
                print(content.text)


if __name__ == "__main__":
    asyncio.run(main())