# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""LLM provider factory: openai / claude / grok."""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel

PROVIDERS = ("openai", "claude", "grok")
DEFAULT_PROVIDER = "claude"

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "claude": "claude-sonnet-4-5",
    "grok": "grok-3-mini",
}

_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "grok": "XAI_API_KEY",
}

XAI_BASE_URL = "https://api.x.ai/v1"


def resolve_provider(cli_provider: str | None = None) -> str:
    """CLI ``--provider`` → ``NUROPB_LLM_PROVIDER`` → default ``claude``."""
    raw = (cli_provider or os.environ.get("NUROPB_LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if raw not in PROVIDERS:
        raise SystemExit(
            f"unknown LLM provider {raw!r}; choose one of: {', '.join(PROVIDERS)}"
        )
    return raw


def make_chat_model(provider: str, *, model: str | None = None) -> BaseChatModel:
    """Return a tool-calling chat model for ``openai`` / ``claude`` / ``grok``.

    Fails fast with the missing env var name; never falls through to another
    provider.
    """
    provider = provider.strip().lower()
    if provider not in PROVIDERS:
        raise SystemExit(
            f"unknown LLM provider {provider!r}; choose one of: {', '.join(PROVIDERS)}"
        )

    key_name = _KEY_ENV[provider]
    api_key = os.environ.get(key_name, "").strip()
    if not api_key:
        raise SystemExit(
            f"missing {key_name} for provider={provider!r}; "
            f"set it in the environment or examples/langchain_example/.env"
        )

    chosen = (model or os.environ.get("NUROPB_LLM_MODEL") or _DEFAULT_MODELS[provider]).strip()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=chosen, api_key=api_key, temperature=0)

    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=chosen, api_key=api_key, temperature=0)

    # grok — xAI OpenAI-compatible API
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=chosen,
        api_key=api_key,
        base_url=XAI_BASE_URL,
        temperature=0,
    )
