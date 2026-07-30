import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- Case 1: Junior analyst tries a large refund (DISP-002, $899) — should be REJECTED ---
            print("=== Case 1: Junior analyst (ANL-001) attempts large refund on DISP-002 ($899) ===")
            result = await session.call_tool(
                "process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-001"}
            )
            for content in result.content:
                print(content.text)
            print()

            # --- Case 2: Senior analyst approves the same large refund — should be APPROVED ---
            print("=== Case 2: Senior analyst (ANL-002) attempts same refund on DISP-002 ===")
            result = await session.call_tool(
                "process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-002"}
            )
            for content in result.content:
                print(content.text)
            print()

            # --- Case 3: Try refunding the SAME dispute again — should be REJECTED (already resolved) ---
            print("=== Case 3: Attempt to refund DISP-002 again (already resolved) ===")
            result = await session.call_tool(
                "process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-002"}
            )
            for content in result.content:
                print(content.text)
            print()

            # --- Case 4: Small refund by a junior analyst (DISP-001, $29.99) — should be APPROVED ---
            print("=== Case 4: Junior analyst (ANL-001) approves small refund on DISP-001 ($29.99) ===")
            result = await session.call_tool(
                "process_refund", {"dispute_id": "DISP-001", "analyst_id": "ANL-001"}
            )
            for content in result.content:
                print(content.text)


if __name__ == "__main__":
    asyncio.run(main())