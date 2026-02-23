"""
Pinecone vector memory client.
Uses Pinecone's integrated embeddings (llama-text-embed-v2) — no external
embedding model or API key required beyond PINECONE_API_KEY.
"""

import os
import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_pinecone_index = None

PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX", "research-memory")
EMBED_MODEL = "llama-text-embed-v2"
NAMESPACE = "conversations"


def _get_index():
    global _pinecone_index
    if _pinecone_index is None:
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("PINECONE_API_KEY is not set")

        from pinecone import Pinecone
        pc = Pinecone(api_key=api_key)

        existing = [idx.name for idx in pc.list_indexes()]
        if PINECONE_INDEX_NAME not in existing:
            pc.create_index_for_model(
                name=PINECONE_INDEX_NAME,
                cloud="aws",
                region="us-east-1",
                embed={
                    "model": EMBED_MODEL,
                    "field_map": {"text": "content"},
                },
            )
            logger.info(f"Created Pinecone index '{PINECONE_INDEX_NAME}' with {EMBED_MODEL}")

        _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Simple character-level chunking with overlap."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def upsert_chunks(
    conversation_id: str,
    text: str,
    summary_snippet: Optional[str] = None,
) -> None:
    """Chunk and upsert text into Pinecone using integrated embeddings."""
    if not text.strip():
        return

    try:
        index = _get_index()
        chunks = _chunk_text(text)
        records = []

        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{conversation_id}:{i}:{chunk}".encode()).hexdigest()
            records.append({
                "_id": chunk_id,
                "content": chunk,  # field embedded by llama-text-embed-v2
                "conversation_id": conversation_id,
                "chunk_index": i,
                "summary_snippet": summary_snippet or "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        if records:
            index.upsert_records(NAMESPACE, records)
            logger.info(f"Upserted {len(records)} chunks for conversation {conversation_id}")

    except Exception as e:
        logger.warning(f"Pinecone upsert failed (non-fatal): {e}")


def query_similar(query: str, top_k: int = 5) -> list[dict]:
    """Search for similar chunks using integrated embeddings."""
    try:
        index = _get_index()
        results = index.search(
            namespace=NAMESPACE,
            query={
                "inputs": {"text": query},
                "top_k": top_k,
            },
        )

        return [
            {
                "score": hit["_score"],
                "text": hit["fields"].get("content", ""),
                "conversation_id": hit["fields"].get("conversation_id", ""),
                "summary_snippet": hit["fields"].get("summary_snippet", ""),
            }
            for hit in results["result"]["hits"]
        ]
    except Exception as e:
        logger.warning(f"Pinecone query failed (non-fatal): {e}")
        return []
