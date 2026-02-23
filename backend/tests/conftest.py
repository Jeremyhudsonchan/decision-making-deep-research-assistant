"""
Shared pytest fixtures for the backend test suite.

Key design decisions:
- API keys are set at module level so they're in os.environ before any app
  module is imported (modules read env vars at import time).
- The lru_cache on get_llm() is cleared between tests to prevent stale mocks.
- SQLite is pointed at a temp file (set before any import); conversation_store
  tests further override the engine via monkeypatch for per-test isolation.
"""

import os
import tempfile
import atexit
import shutil

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock

# ---------------------------------------------------------------------------
# Set env vars BEFORE any app module is imported
# ---------------------------------------------------------------------------
_TEST_DB_DIR = tempfile.mkdtemp(prefix="research_test_")
atexit.register(shutil.rmtree, _TEST_DB_DIR, ignore_errors=True)

os.environ.update({
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "OPENAI_API_KEY": "test-openai-key",
    "TAVILY_API_KEY": "test-tavily-key",
    "PINECONE_API_KEY": "test-pinecone-key",
    "LLM_PROVIDER": "anthropic",
    "LLM_MODEL": "claude-sonnet-4-6",
    "SQLITE_DB_PATH": os.path.join(_TEST_DB_DIR, "test_research.db"),
})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    """Ensure test env vars are set for every test function."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setenv("PINECONE_API_KEY", "test-pinecone-key")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-6")


@pytest.fixture(autouse=True)
def clear_llm_cache():
    """Clear lru_cache on get_llm() before and after each test."""
    from app.agent.llm import get_llm
    get_llm.cache_clear()
    yield
    get_llm.cache_clear()


@pytest.fixture
def mock_llm():
    """
    MagicMock that behaves like a LangChain BaseChatModel.
    ainvoke() returns a response with content='["q1","q2","q3"]' by default.
    Override mock_llm.ainvoke.return_value in individual tests as needed.
    """
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=MagicMock(content='["q1", "q2", "q3"]')
    )
    return llm


@pytest_asyncio.fixture
async def async_client(monkeypatch):
    """
    httpx.AsyncClient wired to the FastAPI app.
    init_db is mocked to avoid touching the filesystem during route tests.
    """
    from httpx import AsyncClient, ASGITransport

    monkeypatch.setattr(
        "app.memory.conversation_store.init_db", AsyncMock()
    )
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
