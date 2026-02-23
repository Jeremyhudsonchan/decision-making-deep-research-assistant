"""
Tests for Pydantic schemas in app/schemas.py.
"""

import pytest
from pydantic import ValidationError

from app.schemas import (
    ResearchRequest,
    ClarifyRequest,
    ResearchInvokeResponse,
    ResearchStatus,
)


class TestResearchRequest:
    def test_valid_minimal(self):
        req = ResearchRequest(query="What is AI?")
        assert req.query == "What is AI?"
        assert req.interactive_mode is False
        assert req.conversation_id is None

    def test_interactive_mode_default_false(self):
        req = ResearchRequest(query="test")
        assert req.interactive_mode is False

    def test_interactive_mode_explicit_true(self):
        req = ResearchRequest(query="test", interactive_mode=True)
        assert req.interactive_mode is True

    def test_conversation_id_default_none(self):
        req = ResearchRequest(query="test")
        assert req.conversation_id is None

    def test_conversation_id_provided(self):
        req = ResearchRequest(query="test", conversation_id="abc-123")
        assert req.conversation_id == "abc-123"

    def test_empty_query_raises(self):
        with pytest.raises(ValidationError):
            ResearchRequest(query="")

    def test_missing_query_raises(self):
        with pytest.raises(ValidationError):
            ResearchRequest()


class TestClarifyRequest:
    def test_empty_list_is_valid(self):
        req = ClarifyRequest(sub_questions=[])
        assert req.sub_questions == []

    def test_with_questions(self):
        req = ClarifyRequest(sub_questions=["q1", "q2"])
        assert req.sub_questions == ["q1", "q2"]

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            ClarifyRequest()


class TestResearchInvokeResponse:
    def test_completed_status(self):
        resp = ResearchInvokeResponse(
            conversation_id="abc",
            status="completed",
            final_answer="The answer.",
        )
        assert resp.status == "completed"
        assert resp.final_answer == "The answer."

    def test_awaiting_input_status(self):
        resp = ResearchInvokeResponse(
            conversation_id="abc",
            status="awaiting_input",
            sub_questions=["q1", "q2"],
        )
        assert resp.status == "awaiting_input"
        assert resp.sub_questions == ["q1", "q2"]

    def test_error_status(self):
        resp = ResearchInvokeResponse(
            conversation_id="abc",
            status="error",
            error="Something went wrong",
        )
        assert resp.status == "error"
        assert resp.error == "Something went wrong"

    def test_defaults(self):
        resp = ResearchInvokeResponse(conversation_id="abc", status="completed")
        assert resp.sub_questions == []
        assert resp.research_results == []
        assert resp.final_answer is None
        assert resp.error is None


class TestResearchStatus:
    def test_sub_questions_default_empty(self):
        status = ResearchStatus(
            conversation_id="abc",
            status="running",
            query="test",
        )
        assert status.sub_questions == []

    def test_final_answer_optional(self):
        status = ResearchStatus(
            conversation_id="abc",
            status="completed",
            query="test",
            final_answer="Done",
        )
        assert status.final_answer == "Done"
