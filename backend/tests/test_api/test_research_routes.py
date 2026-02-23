"""
Integration tests for the FastAPI research routes.

All LangGraph graph methods and conversation store functions are mocked
so no real LLM calls or DB writes occur.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.graph import compiled_graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_completed_state(final_answer="Synthesized answer.") -> dict:
    return {
        "query": "test query",
        "sub_questions": ["q1", "q2"],
        "research_results": [
            {"sub_question": "q1", "tool_used": "web", "result": "result1"},
            {"sub_question": "q2", "tool_used": "finance", "result": "result2"},
        ],
        "final_answer": final_answer,
        "interactive_mode": False,
        "awaiting_user_input": False,
        "user_clarification": None,
        "conversation_id": "test-conv-id",
        "messages": [],
        "memory_context": "",
        "current_node": "save_memory",
        "error": None,
    }


def _fake_interrupted_state() -> dict:
    return {
        "query": "test query",
        "sub_questions": ["q1", "q2", "q3"],
        "research_results": [],
        "final_answer": "",
        "interactive_mode": True,
        "awaiting_user_input": True,
        "user_clarification": None,
        "conversation_id": "test-conv-id",
        "messages": [],
        "memory_context": "",
        "current_node": "human_review",
        "error": None,
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    async def test_health_returns_ok(self, async_client):
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /research/invoke (non-streaming)
# ---------------------------------------------------------------------------


class TestInvokeResearch:
    async def test_autonomous_mode_returns_completed(self, async_client, mocker):
        mocker.patch.object(
            compiled_graph,
            "ainvoke",
            new=AsyncMock(return_value=_fake_completed_state()),
        )
        mock_state = MagicMock()
        mock_state.next = ()  # empty tuple = graph completed
        mocker.patch.object(compiled_graph, "get_state", return_value=mock_state)

        response = await async_client.post(
            "/research/invoke",
            json={"query": "Impact of AI on employment", "interactive_mode": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["final_answer"] == "Synthesized answer."
        assert len(data["research_results"]) == 2

    async def test_interactive_mode_returns_awaiting_input(self, async_client, mocker):
        mocker.patch.object(
            compiled_graph,
            "ainvoke",
            new=AsyncMock(return_value=_fake_interrupted_state()),
        )
        mock_state = MagicMock()
        mock_state.next = ("research",)  # non-empty = interrupted
        mocker.patch.object(compiled_graph, "get_state", return_value=mock_state)

        response = await async_client.post(
            "/research/invoke",
            json={"query": "Test question", "interactive_mode": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "awaiting_input"
        assert data["sub_questions"] == ["q1", "q2", "q3"]

    async def test_missing_query_returns_422(self, async_client):
        response = await async_client.post("/research/invoke", json={})
        assert response.status_code == 422

    async def test_empty_query_returns_422(self, async_client):
        response = await async_client.post(
            "/research/invoke", json={"query": ""}
        )
        assert response.status_code == 422

    async def test_invoke_error_returns_error_status(self, async_client, mocker):
        mocker.patch.object(
            compiled_graph,
            "ainvoke",
            new=AsyncMock(side_effect=RuntimeError("LLM unavailable")),
        )

        response = await async_client.post(
            "/research/invoke", json={"query": "test"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "LLM unavailable" in data["error"]


# ---------------------------------------------------------------------------
# POST /research/{id}/clarify/invoke
# ---------------------------------------------------------------------------


class TestClarifyInvoke:
    async def test_clarify_invoke_returns_completed(self, async_client, mocker):
        mocker.patch.object(
            compiled_graph,
            "ainvoke",
            new=AsyncMock(return_value=_fake_completed_state()),
        )

        response = await async_client.post(
            "/research/test-conv-id/clarify/invoke",
            json={"sub_questions": ["edited q1", "edited q2"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["final_answer"] == "Synthesized answer."

    async def test_clarify_invoke_error_returns_error_status(
        self, async_client, mocker
    ):
        mocker.patch.object(
            compiled_graph,
            "ainvoke",
            new=AsyncMock(side_effect=RuntimeError("Graph error")),
        )

        response = await async_client.post(
            "/research/missing-conv/clarify/invoke",
            json={"sub_questions": ["q1"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# GET /research/{id}/status
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    async def test_not_found_returns_404(self, async_client, mocker):
        mocker.patch(
            "app.api.routes.research.get_conversation",
            new=AsyncMock(return_value=None),
        )

        response = await async_client.get("/research/nonexistent-id/status")
        assert response.status_code == 404

    async def test_found_returns_status(self, async_client, mocker):
        mock_conv = MagicMock()
        mock_conv.query = "What is AI?"

        mock_msg = MagicMock()
        mock_msg.role = "assistant"
        mock_msg.content = "AI is transformative."

        mocker.patch(
            "app.api.routes.research.get_conversation",
            new=AsyncMock(return_value=mock_conv),
        )
        mocker.patch(
            "app.api.routes.research.get_conversation_history",
            new=AsyncMock(return_value=[mock_msg]),
        )

        response = await async_client.get("/research/some-conv-id/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["final_answer"] == "AI is transformative."
        assert data["query"] == "What is AI?"

    async def test_no_assistant_message_returns_running(self, async_client, mocker):
        mock_conv = MagicMock()
        mock_conv.query = "Pending research"

        mock_msg = MagicMock()
        mock_msg.role = "user"
        mock_msg.content = "user message"

        mocker.patch(
            "app.api.routes.research.get_conversation",
            new=AsyncMock(return_value=mock_conv),
        )
        mocker.patch(
            "app.api.routes.research.get_conversation_history",
            new=AsyncMock(return_value=[mock_msg]),
        )

        response = await async_client.get("/research/pending-conv/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["final_answer"] is None


# ---------------------------------------------------------------------------
# POST /research (SSE streaming)
# ---------------------------------------------------------------------------


class TestResearchSSE:
    async def test_sse_stream_yields_expected_events(self, async_client, mocker):
        async def fake_astream_events(*args, **kwargs):
            events = [
                {"event": "on_chain_start", "name": "decompose"},
                {
                    "event": "on_chain_end",
                    "name": "decompose",
                    "data": {"output": {"sub_questions": ["q1", "q2"]}},
                },
                {"event": "on_chain_start", "name": "research"},
                {
                    "event": "on_chain_end",
                    "name": "research",
                    "data": {
                        "output": {
                            "research_results": [
                                {
                                    "sub_question": "q1",
                                    "tool_used": "web",
                                    "result": "some web result",
                                }
                            ]
                        }
                    },
                },
                {"event": "on_chain_start", "name": "synthesize"},
                {
                    "event": "on_chain_end",
                    "name": "synthesize",
                    "data": {"output": {"final_answer": "Final synthesized answer."}},
                },
                {
                    "event": "on_chain_end",
                    "name": "save_memory",
                    "data": {"output": {}},
                },
            ]
            for event in events:
                yield event

        mocker.patch.object(
            compiled_graph, "astream_events", new=fake_astream_events
        )

        response = await async_client.post(
            "/research",
            json={"query": "Test query", "interactive_mode": False},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # Parse SSE events from the response body
        body = response.text
        event_types = []
        for line in body.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
                if payload:
                    data = json.loads(payload)
                    event_types.append(data["type"])

        assert "start" in event_types
        assert "sub_questions" in event_types
        assert "research_results" in event_types
        assert "final_answer" in event_types
        assert "completed" in event_types

    async def test_sse_stream_on_error_yields_error_event(self, async_client, mocker):
        async def fake_astream_events_error(*args, **kwargs):
            raise RuntimeError("Graph crashed")
            yield  # make it an async generator

        mocker.patch.object(
            compiled_graph, "astream_events", new=fake_astream_events_error
        )

        response = await async_client.post(
            "/research",
            json={"query": "Test query"},
        )

        assert response.status_code == 200
        body = response.text
        found_error = False
        for line in body.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
                if payload:
                    data = json.loads(payload)
                    if data["type"] == "error":
                        found_error = True
                        break
        assert found_error


# ---------------------------------------------------------------------------
# POST /research/{id}/clarify (SSE streaming)
# ---------------------------------------------------------------------------


class TestClarifySSE:
    async def test_clarify_sse_stream_yields_resume_and_completed(
        self, async_client, mocker
    ):
        async def fake_resume_events(*args, **kwargs):
            events = [
                {"event": "on_chain_start", "name": "research"},
                {
                    "event": "on_chain_end",
                    "name": "research",
                    "data": {
                        "output": {
                            "research_results": [
                                {
                                    "sub_question": "edited q1",
                                    "tool_used": "web",
                                    "result": "result",
                                }
                            ]
                        }
                    },
                },
                {
                    "event": "on_chain_end",
                    "name": "synthesize",
                    "data": {"output": {"final_answer": "Resumed answer."}},
                },
                {
                    "event": "on_chain_end",
                    "name": "save_memory",
                    "data": {"output": {}},
                },
            ]
            for event in events:
                yield event

        mocker.patch.object(
            compiled_graph, "astream_events", new=fake_resume_events
        )

        response = await async_client.post(
            "/research/test-conv-id/clarify",
            json={"sub_questions": ["edited q1"]},
        )

        assert response.status_code == 200
        body = response.text
        event_types = []
        for line in body.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
                if payload:
                    data = json.loads(payload)
                    event_types.append(data["type"])

        assert "resume" in event_types
        assert "completed" in event_types
        assert "final_answer" in event_types
