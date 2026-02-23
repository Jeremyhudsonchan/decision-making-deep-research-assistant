"""
Research API routes.

POST /research         — Start a new research session (streams via SSE)
POST /research/{id}/clarify — Submit user-edited sub-questions (interactive mode)
GET  /research/{id}/status  — Polling fallback
"""

import json
import uuid
import logging
import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.schemas import ResearchRequest, ResearchResponse, ClarifyRequest, ResearchStatus, SubQuestion, ResearchInvokeResponse
from app.agent.graph import compiled_graph
from app.agent.state import AgentState
from app.memory.conversation_store import get_conversation, get_conversation_history

logger = logging.getLogger(__name__)
router = APIRouter()

# Track in-flight research sessions: conversation_id → current AgentState snapshot
# (used for interactive mode status checks)
_session_cache: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# SSE event helpers
# ---------------------------------------------------------------------------


def _sse_event(event_type: str, data: dict) -> str:
    payload = json.dumps({"type": event_type, **data})
    return f"data: {payload}\n\n"


async def _stream_research(
    conversation_id: str,
    initial_state: AgentState,
    config: dict,
) -> AsyncGenerator[str, None]:
    """Run the LangGraph graph and yield SSE events for each node transition."""
    try:
        yield _sse_event("start", {"conversation_id": conversation_id, "status": "running"})

        async for event in compiled_graph.astream_events(
            initial_state,
            config=config,
            version="v2",
        ):
            kind = event.get("event", "")
            name = event.get("name", "")

            # Node start events
            if kind == "on_chain_start" and name in (
                "retrieve_memory", "decompose", "human_review",
                "research", "synthesize", "save_memory",
            ):
                yield _sse_event("node_start", {"node": name})

            # Node end events — emit relevant state updates
            elif kind == "on_chain_end" and name in (
                "retrieve_memory", "decompose", "human_review",
                "research", "synthesize", "save_memory",
            ):
                output = event.get("data", {}).get("output", {})

                if name == "decompose" and "sub_questions" in output:
                    yield _sse_event("sub_questions", {
                        "node": name,
                        "sub_questions": output["sub_questions"],
                    })

                elif name == "research" and "research_results" in output:
                    results_summary = [
                        {
                            "sub_question": r["sub_question"],
                            "tool_used": r["tool_used"],
                            "snippet": r["result"][:300],
                        }
                        for r in output["research_results"]
                    ]
                    yield _sse_event("research_results", {
                        "node": name,
                        "results": results_summary,
                    })

                elif name == "synthesize" and "final_answer" in output:
                    yield _sse_event("final_answer", {
                        "node": name,
                        "answer": output["final_answer"],
                    })

                elif name == "save_memory":
                    yield _sse_event("completed", {
                        "conversation_id": conversation_id,
                        "status": "completed",
                    })

                yield _sse_event("node_end", {"node": name})

        # After the stream ends, check if the graph was interrupted (interactive mode)
        state = compiled_graph.get_state(config)
        if state.next:
            yield _sse_event("awaiting_input", {
                "node": "human_review",
                "sub_questions": state.values.get("sub_questions", []),
                "message": "Review and edit sub-questions, then POST to /research/{id}/clarify",
            })

    except Exception as e:
        logger.exception(f"Research stream error for {conversation_id}: {e}")
        yield _sse_event("error", {"error": str(e), "conversation_id": conversation_id})


# ---------------------------------------------------------------------------
# POST /research
# ---------------------------------------------------------------------------


@router.post("", response_model=ResearchResponse)
async def start_research(request: ResearchRequest):
    """
    Start a research session.
    Returns conversation_id immediately; client should connect to SSE stream.
    For simplicity this endpoint itself streams — use the StreamingResponse directly.
    """
    conversation_id = request.conversation_id or str(uuid.uuid4())
    logger.info("POST /research query=%r interactive=%s conv_id=%s",
                request.query[:80], request.interactive_mode, conversation_id)

    initial_state: AgentState = {
        "query": request.query,
        "sub_questions": [],
        "research_results": [],
        "final_answer": "",
        "interactive_mode": request.interactive_mode,
        "awaiting_user_input": False,
        "user_clarification": None,
        "conversation_id": conversation_id,
        "messages": [HumanMessage(content=request.query)],
        "memory_context": "",
        "current_node": "",
        "error": None,
    }

    config = {"configurable": {"thread_id": conversation_id}}

    return StreamingResponse(
        _stream_research(conversation_id, initial_state, config),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Conversation-Id": conversation_id,
        },
    )


# ---------------------------------------------------------------------------
# POST /research/invoke  (non-streaming JSON — programmatic callers)
# ---------------------------------------------------------------------------


@router.post("/invoke", response_model=ResearchInvokeResponse)
async def invoke_research(request: ResearchRequest):
    """
    Start a research session synchronously and return JSON.

    - Autonomous mode: blocks until complete, returns final_answer.
    - Interactive mode: blocks until interrupt, returns status "awaiting_input"
      with sub_questions for the caller to review then POST to /{id}/clarify/invoke.
    """
    conversation_id = request.conversation_id or str(uuid.uuid4())

    initial_state: AgentState = {
        "query": request.query,
        "sub_questions": [],
        "research_results": [],
        "final_answer": "",
        "interactive_mode": request.interactive_mode,
        "awaiting_user_input": False,
        "user_clarification": None,
        "conversation_id": conversation_id,
        "messages": [HumanMessage(content=request.query)],
        "memory_context": "",
        "current_node": "",
        "error": None,
    }

    config = {"configurable": {"thread_id": conversation_id}}

    try:
        result = await compiled_graph.ainvoke(initial_state, config=config)
    except Exception as e:
        logger.exception(f"Invoke error for {conversation_id}: {e}")
        return ResearchInvokeResponse(
            conversation_id=conversation_id,
            status="error",
            error=str(e),
        )

    # If the graph was interrupted (interactive mode), state.next will be non-empty.
    state = compiled_graph.get_state(config)
    if state.next:
        return ResearchInvokeResponse(
            conversation_id=conversation_id,
            status="awaiting_input",
            sub_questions=result.get("sub_questions", []),
        )

    research_results = [
        {
            "sub_question": r["sub_question"],
            "tool_used": r["tool_used"],
            "snippet": r["result"][:300],
        }
        for r in result.get("research_results", [])
    ]
    return ResearchInvokeResponse(
        conversation_id=conversation_id,
        status="completed",
        sub_questions=result.get("sub_questions", []),
        final_answer=result.get("final_answer"),
        research_results=research_results,
    )


# ---------------------------------------------------------------------------
# POST /research/{id}/clarify
# ---------------------------------------------------------------------------


@router.post("/{conversation_id}/clarify")
async def clarify(conversation_id: str, request: ClarifyRequest):
    """
    Resume an interrupted (interactive mode) graph with user-edited sub-questions.
    """
    logger.info("POST /research/%s/clarify questions=%s", conversation_id, request.sub_questions)
    config = {"configurable": {"thread_id": conversation_id}}

    async def _resume_stream() -> AsyncGenerator[str, None]:
        try:
            yield _sse_event("resume", {
                "conversation_id": conversation_id,
                "sub_questions": request.sub_questions,
            })

            # Resume the graph from the interrupt checkpoint
            async for event in compiled_graph.astream_events(
                Command(resume=request.sub_questions),
                config=config,
                version="v2",
            ):
                kind = event.get("event", "")
                name = event.get("name", "")

                if kind == "on_chain_start" and name in ("research", "synthesize", "save_memory"):
                    yield _sse_event("node_start", {"node": name})

                elif kind == "on_chain_end":
                    output = event.get("data", {}).get("output", {})

                    if name == "research" and "research_results" in output:
                        results_summary = [
                            {
                                "sub_question": r["sub_question"],
                                "tool_used": r["tool_used"],
                                "snippet": r["result"][:300],
                            }
                            for r in output["research_results"]
                        ]
                        yield _sse_event("research_results", {
                            "node": name,
                            "results": results_summary,
                        })

                    elif name == "synthesize" and "final_answer" in output:
                        yield _sse_event("final_answer", {
                            "node": name,
                            "answer": output["final_answer"],
                        })

                    elif name == "save_memory":
                        yield _sse_event("completed", {
                            "conversation_id": conversation_id,
                            "status": "completed",
                        })

                    if name in ("research", "synthesize", "save_memory"):
                        yield _sse_event("node_end", {"node": name})

        except Exception as e:
            logger.exception(f"Clarify stream error for {conversation_id}: {e}")
            yield _sse_event("error", {"error": str(e)})

    return StreamingResponse(
        _resume_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# POST /research/{id}/clarify/invoke  (non-streaming JSON)
# ---------------------------------------------------------------------------


@router.post("/{conversation_id}/clarify/invoke", response_model=ResearchInvokeResponse)
async def clarify_invoke(conversation_id: str, request: ClarifyRequest):
    """
    Resume an interrupted interactive session synchronously and return JSON.
    Blocks until the full research + synthesis completes.
    """
    config = {"configurable": {"thread_id": conversation_id}}

    try:
        result = await compiled_graph.ainvoke(
            Command(resume=request.sub_questions),
            config=config,
        )
    except Exception as e:
        logger.exception(f"Clarify invoke error for {conversation_id}: {e}")
        return ResearchInvokeResponse(
            conversation_id=conversation_id,
            status="error",
            error=str(e),
        )

    research_results = [
        {
            "sub_question": r["sub_question"],
            "tool_used": r["tool_used"],
            "snippet": r["result"][:300],
        }
        for r in result.get("research_results", [])
    ]
    return ResearchInvokeResponse(
        conversation_id=conversation_id,
        status="completed",
        final_answer=result.get("final_answer"),
        research_results=research_results,
    )


# ---------------------------------------------------------------------------
# GET /research/{id}/status
# ---------------------------------------------------------------------------


@router.get("/{conversation_id}/status", response_model=ResearchStatus)
async def get_status(conversation_id: str):
    """Polling fallback to get the current status of a research session."""
    conv = await get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")

    messages = await get_conversation_history(conversation_id)

    final_answer = None
    for msg in reversed(messages):
        if msg.role == "assistant":
            final_answer = msg.content
            break

    return ResearchStatus(
        conversation_id=conversation_id,
        status="completed" if final_answer else "running",
        query=conv.query,
        final_answer=final_answer,
    )
