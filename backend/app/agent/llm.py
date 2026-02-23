"""
LLM factory — reads LLM_PROVIDER and LLM_MODEL from environment and returns
the appropriate LangChain chat model instance.

All agent nodes should import `get_llm()` rather than hardcoding a model.
"""

import os
from functools import lru_cache
from langchain_core.language_models.chat_models import BaseChatModel


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    model = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        return ChatOpenAI(model=model, api_key=api_key, temperature=0)

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        return ChatAnthropic(model=model, api_key=api_key, temperature=0)

    elif provider == "ollama":
        from langchain_ollama import ChatOllama

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(model=model, base_url=base_url, temperature=0)

    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: '{provider}'. Must be 'openai', 'anthropic', or 'ollama'."
        )
