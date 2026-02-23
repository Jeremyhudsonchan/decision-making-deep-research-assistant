"""
Tests for the SQLite conversation store.

Each test gets a fresh in-memory SQLite engine by monkeypatching the
module-level 'engine' and 'AsyncSessionLocal' in conversation_store.
This ensures full isolation without touching the filesystem.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.memory.conversation_store as cs


@pytest_asyncio.fixture
async def db(monkeypatch, tmp_path):
    """
    Provide a fresh SQLite database per test.
    Uses a temp file (not :memory:) to avoid aiosqlite connection-sharing issues.
    """
    db_file = tmp_path / "test.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    TestSession = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    monkeypatch.setattr(cs, "engine", test_engine)
    monkeypatch.setattr(cs, "AsyncSessionLocal", TestSession)

    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield test_engine

    await test_engine.dispose()


class TestInitDb:
    async def test_init_db_creates_tables(self, db):
        """Tables already created by fixture; verify we can call init_db again safely."""
        # Re-running init_db should be idempotent (create_all is safe to call multiple times)
        await cs.init_db()


class TestSaveAndGetConversation:
    async def test_save_and_retrieve(self, db):
        conv = await cs.save_conversation("conv-1", "What is AI?")
        assert conv.id == "conv-1"
        assert conv.query == "What is AI?"

        fetched = await cs.get_conversation("conv-1")
        assert fetched is not None
        assert fetched.id == "conv-1"
        assert fetched.query == "What is AI?"

    async def test_save_upserts_existing(self, db):
        conv1 = await cs.save_conversation("conv-2", "Query A")
        original_updated = conv1.updated_at

        # Upsert with a summary
        conv2 = await cs.save_conversation("conv-2", "Query A", summary="Summary here")
        assert conv2.summary == "Summary here"
        # updated_at should be refreshed (or at least the record updated)

    async def test_get_nonexistent_returns_none(self, db):
        result = await cs.get_conversation("does-not-exist")
        assert result is None


class TestSaveMessage:
    async def test_save_and_retrieve_message(self, db):
        await cs.save_conversation("conv-3", "Test query")
        msg = await cs.save_message("conv-3", "user", "Hello, research assistant!")

        assert msg.conversation_id == "conv-3"
        assert msg.role == "user"
        assert msg.content == "Hello, research assistant!"

    async def test_get_conversation_history_ordered(self, db):
        await cs.save_conversation("conv-4", "Ordering test")
        await cs.save_message("conv-4", "user", "First message")
        await cs.save_message("conv-4", "assistant", "Second message")
        await cs.save_message("conv-4", "user", "Third message")

        history = await cs.get_conversation_history("conv-4")
        assert len(history) == 3
        assert history[0].content == "First message"
        assert history[1].content == "Second message"
        assert history[2].content == "Third message"

    async def test_multiple_conversations_isolated(self, db):
        await cs.save_conversation("conv-A", "Query A")
        await cs.save_conversation("conv-B", "Query B")

        await cs.save_message("conv-A", "user", "Message for A")
        await cs.save_message("conv-B", "user", "Message for B")

        hist_a = await cs.get_conversation_history("conv-A")
        hist_b = await cs.get_conversation_history("conv-B")

        assert len(hist_a) == 1
        assert hist_a[0].content == "Message for A"
        assert len(hist_b) == 1
        assert hist_b[0].content == "Message for B"

    async def test_empty_history_for_new_conversation(self, db):
        await cs.save_conversation("conv-empty", "Empty query")
        history = await cs.get_conversation_history("conv-empty")
        assert history == []
