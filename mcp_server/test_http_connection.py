import asyncio
import os
import subprocess
import sys
import time
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SERVER_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")


async def run_test():
    url = "http://127.0.0.1:8000/mcp/"

    async with streamable_http_client(url) as (read, write):
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


import socket

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_port_open(host="127.0.0.1", port=8000):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


async def main():
    server_proc = None
    try:
        await run_test()
    except Exception:
        print("HTTP server not detected on port 8000. Launching temporary server.py --http...")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.pathsep.join([REPO_ROOT, os.path.dirname(SERVER_PY)] + sys.path)
        server_proc = subprocess.Popen([sys.executable, SERVER_PY, "--http"], cwd=REPO_ROOT, env=env)

        # Wait up to 5 seconds for port 8000 to listen
        for _ in range(50):
            if is_port_open():
                break
            time.sleep(0.1)

        try:
            await run_test()
        finally:
            if server_proc:
                server_proc.terminate()
                server_proc.wait()


if __name__ == "__main__":
    asyncio.run(main())