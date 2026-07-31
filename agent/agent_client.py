"""
Part 1 (Person C): the Agent/Client.

The thing an analyst actually interacts with. Connects to Person B's server,
does the real initialize handshake, discovers tools/resources/prompts at
runtime (not a hardcoded list), keeps that discovery live across the session
(refreshes automatically on notifications/tools/list_changed), and refuses
client-side to attempt any tool that needs a capability the server never
declared.

Run directly for a smoke test:  python agent_client.py
"""

import asyncio
import logging
from typing import Any, Optional

import mcp.types as types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dispute-agent")


class DisputeAgentClient:
    """Async context manager wrapping one MCP session against the
    Sterling Vance dispute server."""

    def __init__(
        self,
        server_params: StdioServerParameters,
        elicitation_responder=None,
        sampling_responder=None,
    ):
        self.server_params = server_params
        self._stdio_ctx = None
        self._session_ctx = None
        self.session: Optional[ClientSession] = None
        self.server_capabilities: Optional[types.ServerCapabilities] = None
        self.tools: dict[str, types.Tool] = {}

        # Allow the caller (a human-facing CLI, an automated demo/test) to
        # plug in how elicitation questions get answered and how sampling
        # requests get a model response. Default to safe, deterministic
        # behavior so nothing hangs if nobody supplies one.
        self._elicitation_responder = elicitation_responder or self._default_elicitation_responder
        self._sampling_responder = sampling_responder or self._default_sampling_responder

    async def _default_elicitation_responder(self, message: str, requested_schema: dict) -> types.ElicitResult:
        """Fallback: print the server's question and read the analyst's
        decision from the terminal. Used when nobody supplies a custom
        responder (e.g. an automated test)."""
        print(f"\n[ELICITATION REQUEST FROM SERVER]\n{message}\n")
        answer = input("Approve? [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return types.ElicitResult(action="accept", content={})
        return types.ElicitResult(action="decline")

    async def _default_sampling_responder(
        self, messages: list, system_prompt, max_tokens: int
    ) -> types.CreateMessageResult:
        """Real sampling: calls OpenRouter (OpenAI-compatible) to generate a
        genuine LLM summary of the dispute evidence.
        Falls back gracefully to echo if the API key is missing or the call fails."""
        import os
        try:
            from openai import AsyncOpenAI
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise EnvironmentError("OPENROUTER_API_KEY not set in agent/.env")

            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
            )

            openai_messages = []
            if system_prompt:
                openai_messages.append({"role": "system", "content": str(system_prompt)})
            for m in messages:
                block = m.content if not isinstance(m.content, list) else m.content[0]
                if isinstance(block, types.TextContent):
                    openai_messages.append({"role": m.role, "content": block.text})

            response = await client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=openai_messages,
                max_tokens=max_tokens or 512,
            )
            summary = response.choices[0].message.content
            log.info("LLM sampling complete via OpenRouter (gpt-4o-mini)")
            return types.CreateMessageResult(
                role="assistant",
                content=types.TextContent(type="text", text=summary),
                model="openai/gpt-4o-mini",
            )
        except Exception as e:
            log.warning("LLM sampling failed (%s) — falling back to echo", e)
            last_text = ""
            for m in messages:
                block = m.content if not isinstance(m.content, list) else m.content[0]
                if isinstance(block, types.TextContent):
                    last_text = block.text
            return types.CreateMessageResult(
                role="assistant",
                content=types.TextContent(type="text", text=last_text),
                model="no-model-attached",
            )


    async def _elicitation_callback(self, context, params) -> types.ElicitResult:
        """SDK-facing hook: the server called session.elicit(...). Forward
        the actual question to whatever responder was configured."""
        return await self._elicitation_responder(params.message, params.requested_schema)

    async def _sampling_callback(self, context, params) -> types.CreateMessageResult:
        """SDK-facing hook: the server called session.create_message(...).
        Forward the actual request to whatever responder was configured."""
        return await self._sampling_responder(params.messages, params.system_prompt, params.max_tokens)

    async def __aenter__(self) -> "DisputeAgentClient":
        self._stdio_ctx = stdio_client(self.server_params)
        read, write = await self._stdio_ctx.__aenter__()

        # message_handler is a generic hook that receives every message the
        # server sends outside of direct request/response — including
        # notifications/tools/list_changed. This is what makes discovery
        # live instead of a one-time snapshot.
        # elicitation_callback / sampling_callback are what actually answer
        # session.elicit(...) / session.create_message(...) requests coming
        # FROM the server — without these, those calls hang forever.
        self._session_ctx = ClientSession(
            read,
            write,
            message_handler=self._handle_message,
            elicitation_callback=self._elicitation_callback,
            sampling_callback=self._sampling_callback,
        )
        self.session = await self._session_ctx.__aenter__()

        # The real opening handshake: server states its capabilities, we
        # receive them, and everything downstream is gated on what actually
        # came back here.
        init_result = await self.session.initialize()
        self.server_capabilities = init_result.capabilities
        log.info("Handshake complete. Server capabilities: %s", self.server_capabilities)

        await self.refresh_tools()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(exc_type, exc, tb)
        if self._stdio_ctx is not None:
            await self._stdio_ctx.__aexit__(exc_type, exc, tb)

    async def _handle_message(self, message: Any) -> None:
        if isinstance(message, Exception):
            log.warning("Session error: %s", message)
            return
        if isinstance(message, types.ToolListChangedNotification):
            log.info("notifications/tools/list_changed received — refreshing tool list")
            await self.refresh_tools()
        elif isinstance(message, types.ServerNotification):
            # fallback for SDK versions that wrap in ServerNotification
            try:
                if isinstance(message.root, types.ToolListChangedNotification):
                    log.info("notifications/tools/list_changed received — refreshing tool list")
                    await self.refresh_tools()
            except AttributeError:
                pass

    async def refresh_tools(self) -> dict[str, types.Tool]:
        result = await self.session.list_tools()
        self.tools = {t.name: t for t in result.tools}
        log.info("Discovered tools: %s", list(self.tools.keys()))
        return self.tools

    def supports_capability(self, capability: str) -> bool:
        """Real capability negotiation, checked against what the server
        actually declared at initialize — not assumed."""
        if self.server_capabilities is None:
            return False
        return getattr(self.server_capabilities, capability, None) is not None

    async def call_tool_gated(
        self,
        tool_name: str,
        arguments: dict,
        requires_capability: Optional[str] = None,
        progress_callback=None,
    ):
        """Call a tool — but if it depends on elicitation/sampling/etc.,
        refuse before ever sending the request if the server didn't declare
        that capability during initialize."""
        if requires_capability is not None and not self.supports_capability(requires_capability):
            raise PermissionError(
                f"Refusing to call '{tool_name}': server did not declare "
                f"'{requires_capability}' capability at initialize."
            )
        if tool_name not in self.tools:
            await self.refresh_tools()
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' is not offered by this server.")

        return await self.session.call_tool(
            tool_name, arguments=arguments, progress_callback=progress_callback
        )

    async def list_resources(self):
        return (await self.session.list_resources()).resources

    async def read_resource(self, uri: str):
        return (await self.session.read_resource(uri)).contents

    async def list_prompts(self):
        return (await self.session.list_prompts()).prompts

    async def get_prompt(self, name: str, arguments: dict):
        return await self.session.get_prompt(name, arguments)


async def _smoke_test():
    """What to prove for Part 1: connect, visible handshake, tool
    discovery, one normal read-only action, end to end."""
    server_params = StdioServerParameters(command="python", args=["mcp_server/server.py"])
    async with DisputeAgentClient(server_params) as client:
        result = await client.call_tool_gated("get_dispute_details", {"dispute_id": "DISP-001"})
        for content in result.content:
            log.info("get_dispute_details result: %s", content.text)


if __name__ == "__main__":
    asyncio.run(_smoke_test())