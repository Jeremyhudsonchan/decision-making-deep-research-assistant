"""
SQLite-backed conversation store using SQLModel (async).
Tables: Conversation, Message
"""

import os
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DB_PATH = os.getenv("SQLITE_DB_PATH", "./data/research.db")
# Ensure directory exists at import time
os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Conversation(SQLModel, table=True):
    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: Optional[str] = None
    query: str


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversation.id", index=True)
    role: str  # "user" | "assistant" | "tool"
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# DB lifecycle
# ---------------------------------------------------------------------------


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


async def save_conversation(conversation_id: str, query: str, summary: Optional[str] = None) -> Conversation:
    async with AsyncSessionLocal() as session:
        existing = await session.get(Conversation, conversation_id)
        if existing:
            existing.summary = summary or existing.summary
            existing.updated_at = datetime.now(timezone.utc)
            session.add(existing)
            await session.commit()
            await session.refresh(existing)
            return existing

        conv = Conversation(id=conversation_id, query=query, summary=summary)
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv


async def save_message(conversation_id: str, role: str, content: str) -> Message:
    async with AsyncSessionLocal() as session:
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg


async def get_conversation_history(conversation_id: str) -> list[Message]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.timestamp)
        )
        return result.scalars().all()


async def get_conversation(conversation_id: str) -> Optional[Conversation]:
    async with AsyncSessionLocal() as session:
        return await session.get(Conversation, conversation_id)
