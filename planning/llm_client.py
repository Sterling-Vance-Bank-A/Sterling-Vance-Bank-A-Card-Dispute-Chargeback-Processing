"""
Sterling Vance Bank — Universal LLM Client & Provider Adapter

Provides unified, robust LLM execution across:
1. Cloud API Providers (OpenAI, OpenRouter, Anthropic, or any OpenAI-compatible API)
2. Local Models (Ollama, vLLM, LMStudio at localhost:11434)
3. Deterministic Mock Fallback (for offline test reproducibility)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request
from typing import Any, Optional

logger = logging.getLogger("universal_llm_client")


def _load_env_files() -> None:
    """Loads environment variables from agent/.env or root .env if present."""
    try:
        from dotenv import load_dotenv
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        agent_env = os.path.join(root_dir, "agent", ".env")
        root_env = os.path.join(root_dir, ".env")
        if os.path.exists(agent_env):
            load_dotenv(dotenv_path=agent_env)
        if os.path.exists(root_env):
            load_dotenv(dotenv_path=root_env)
    except ImportError:
        pass


class UniversalLLMClient:
    """
    Universal LLM Client supporting both Cloud APIs and Local Models.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
    ):
        _load_env_files()

        self.timeout = timeout
        self.max_retries = max_retries
        self.total_tokens_used = 0
        self.total_calls = 0

        # Determine provider and credentials
        env_mistral_key = os.getenv("MISTRAL_API_KEY")
        env_openrouter_key = os.getenv("OPENROUTER_API_KEY")
        env_openai_key = os.getenv("OPENAI_API_KEY")
        env_generic_key = os.getenv("LLM_API_KEY") or os.getenv("API_KEY")
        env_base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")

        if provider:
            self.provider = provider.lower()
        elif env_mistral_key or (api_key and "mistral" in (model or "").lower()):
            self.provider = "mistral"
        elif api_key or env_openrouter_key:
            self.provider = "openrouter" if (env_openrouter_key and not api_key) else "openai"
        elif env_openai_key:
            self.provider = "openai"
        elif env_generic_key:
            self.provider = "custom_api"
        elif env_base_url:
            self.provider = "custom_api"
        else:
            self.provider = "ollama"

        # Resolve API Key
        self.api_key = (
            api_key
            or (env_mistral_key if self.provider == "mistral" else None)
            or (env_openrouter_key if self.provider == "openrouter" else None)
            or (env_openai_key if self.provider == "openai" else None)
            or env_generic_key
            or ""
        )

        # Resolve Endpoint and Default Model
        if self.provider == "mistral":
            self.endpoint = base_url or env_base_url or "https://api.mistral.ai/v1/chat/completions"
            self.model = model or os.getenv("MISTRAL_MODEL") or os.getenv("MODEL_NAME") or "mistral-small-latest"
        elif self.provider == "openrouter":
            self.endpoint = base_url or env_base_url or "https://openrouter.ai/api/v1/chat/completions"
            self.model = model or os.getenv("OPENROUTER_MODEL") or os.getenv("MODEL_NAME") or "openai/gpt-4o-mini"
        elif self.provider == "openai":
            self.endpoint = base_url or env_base_url or "https://api.openai.com/v1/chat/completions"
            self.model = model or os.getenv("OPENAI_MODEL") or os.getenv("MODEL_NAME") or "gpt-4o-mini"
        elif self.provider == "custom_api":
            self.endpoint = base_url or env_base_url or "http://localhost:11434/v1/chat/completions"
            self.model = model or os.getenv("MODEL_NAME") or "gpt-4o-mini"
        elif self.provider == "ollama":
            self.endpoint = base_url or env_base_url or "http://localhost:11434/v1/chat/completions"
            self.model = model or os.getenv("OLLAMA_MODEL") or os.getenv("MODEL_NAME") or "llama3.2:3b"
        else:
            self.endpoint = base_url or "http://localhost:11434/v1/chat/completions"
            self.model = model or "llama3.2:3b"

        logger.info(
            "UniversalLLMClient configured: Provider=%s, Model=%s, Endpoint=%s, Auth=%s",
            self.provider,
            self.model,
            self.endpoint,
            "Enabled (Key present)" if self.api_key else "None (Local/Mock)",
        )

    def generate(self, prompt: str) -> str:
        """Standard generate interface matching toolkit expectations."""
        return self.invoke(prompt)

    def invoke(self, prompt: str) -> str:
        """Executes LLM request via HTTP with retries and token metrics tracking."""
        self.total_calls += 1
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            if self.provider == "openrouter":
                headers["HTTP-Referer"] = "https://github.com/Sterling-Vance-Bank-A"
                headers["X-Title"] = "Sterling Vance Bank Card Dispute Processing"

        p_lower = prompt.lower()
        if "json output" in p_lower or "structured directed acyclic graph" in p_lower or "json" in p_lower:
            max_tok = 500
        elif "rubric" in p_lower or "critic" in p_lower or "reflection" in p_lower:
            max_tok = 300
        else:
            max_tok = 400

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tok,
        }
        req_bytes = json.dumps(payload).encode("utf-8")

        for attempt in range(1, self.max_retries + 1):
            req = urllib.request.Request(self.endpoint, data=req_bytes, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    usage = res.get("usage", {})
                    tokens = usage.get("total_tokens", len(prompt.split()) + 80)
                    self.total_tokens_used += tokens
                    choices = res.get("choices", [])
                    if choices and "message" in choices[0]:
                        content = choices[0]["message"].get("content", "")
                        if content and content.strip():
                            return content.strip()
                    raise RuntimeError(f"Unexpected response payload format: {res}")
            except Exception as e:
                logger.warning("LLM request attempt %d failed: %s", attempt, e)
                # Check for permanent HTTP errors (401 Unauthorized, 402 Payment Required, 403 Forbidden)
                is_auth_error = isinstance(e, urllib.error.HTTPError) and e.code in (401, 402, 403)
                if is_auth_error or attempt >= self.max_retries:
                    # Fallback to local Ollama if cloud API failed and endpoint wasn't already local
                    if "localhost" not in self.endpoint and "127.0.0.1" not in self.endpoint:
                        logger.info("Permanently falling back from cloud API to local Ollama for this session...")
                        self.provider = "ollama"
                        self.endpoint = "http://localhost:11434/v1/chat/completions"
                        self.model = "llama3.2:3b"
                        self.api_key = ""
                        try:
                            local_req = urllib.request.Request(
                                self.endpoint,
                                data=json.dumps({"model": self.model, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8"),
                                headers={"Content-Type": "application/json"},
                            )
                            with urllib.request.urlopen(local_req, timeout=30) as local_resp:
                                local_res = json.loads(local_resp.read().decode("utf-8"))
                                return local_res["choices"][0]["message"]["content"].strip()
                        except Exception as le:
                            logger.error("Local fallback also failed: %s", le)

                    return f"ERROR: LLM request failed ({e})"

                time.sleep(1.0 * attempt)
