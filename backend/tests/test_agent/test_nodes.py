"""
Unit tests for individual LangGraph node functions.

All external dependencies (LLM, Pinecone, conversation store, tools) are
mocked so no real API calls are made.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.state import AgentState, ResearchResult


# ---------------------------------------------------------------------------
# Helper: build a minimal AgentState dict
# ---------------------------------------------------------------------------


def make_state(**overrides) -> AgentState:
    base: AgentState = {
        "query": "What is the impact of AI on employment?",
        "sub_questions": [],
        "research_results": [],
        "final_answer": "",
        "interactive_mode": False,
        "awaiting_user_input": False,
        "user_clarification": None,
        "conversation_id": "test-conv-123",
        "messages": [],
        "memory_context": "",
        "current_node": "",
        "error": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# retrieve_memory
# ---------------------------------------------------------------------------


class TestRetrieveMemory:
    async def test_returns_context_from_pinecone(self):
        from app.agent.nodes import retrieve_memory

        fake_results = [
            {"score": 0.85, "text": "Past answer about AI jobs."},
            {"score": 0.75, "text": "Previous employment analysis."},
        ]
        with patch(
            "app.memory.pinecone_client.query_similar", return_value=fake_results
        ):
            result = await retrieve_memory(make_state())

        assert "memory_context" in result
        assert "Past answer about AI jobs." in result["memory_context"]
        assert "Previous employment analysis." in result["memory_context"]
        assert result["current_node"] == "retrieve_memory"

    async def test_filters_low_score_results(self):
        from app.agent.nodes import retrieve_memory

        fake_results = [
            {"score": 0.85, "text": "High relevance chunk."},
            {"score": 0.50, "text": "Low relevance chunk — should be excluded."},
        ]
        with patch(
            "app.memory.pinecone_client.query_similar", return_value=fake_results
        ):
            result = await retrieve_memory(make_state())

        assert "High relevance chunk." in result["memory_context"]
        assert "Low relevance chunk" not in result["memory_context"]

    async def test_pinecone_failure_returns_empty_context(self):
        from app.agent.nodes import retrieve_memory

        with patch(
            "app.memory.pinecone_client.query_similar",
            side_effect=Exception("Pinecone unavailable"),
        ):
            result = await retrieve_memory(make_state())

        assert result["memory_context"] == ""
        assert result["current_node"] == "retrieve_memory"

    async def test_no_results_returns_empty_context(self):
        from app.agent.nodes import retrieve_memory

        with patch("app.memory.pinecone_client.query_similar", return_value=[]):
            result = await retrieve_memory(make_state())

        assert result["memory_context"] == ""


# ---------------------------------------------------------------------------
# decompose
# ---------------------------------------------------------------------------


class TestDecompose:
    async def test_valid_json_sub_questions(self, mock_llm):
        from app.agent.nodes import decompose

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='["How does AI affect jobs?", "Which sectors are most at risk?", "What new jobs will AI create?"]'
            )
        )
        with patch("app.agent.nodes.get_llm", return_value=mock_llm):
            result = await decompose(make_state())

        assert result["sub_questions"] == [
            "How does AI affect jobs?",
            "Which sectors are most at risk?",
            "What new jobs will AI create?",
        ]
        assert result["current_node"] == "decompose"

    async def test_json_wrapped_in_markdown_code_block(self, mock_llm):
        from app.agent.nodes import decompose

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='```json\n["q1", "q2", "q3"]\n```'
            )
        )
        with patch("app.agent.nodes.get_llm", return_value=mock_llm):
            result = await decompose(make_state())

        assert result["sub_questions"] == ["q1", "q2", "q3"]

    async def test_invalid_json_falls_back_to_original_query(self, mock_llm):
        from app.agent.nodes import decompose

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="I cannot parse this.")
        )
        state = make_state(query="Fallback query")
        with patch("app.agent.nodes.get_llm", return_value=mock_llm):
            result = await decompose(state)

        assert result["sub_questions"] == ["Fallback query"]

    async def test_empty_list_falls_back_to_original_query(self, mock_llm):
        from app.agent.nodes import decompose

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="[]")
        )
        state = make_state(query="My research question")
        with patch("app.agent.nodes.get_llm", return_value=mock_llm):
            result = await decompose(state)

        assert result["sub_questions"] == ["My research question"]

    async def test_caps_at_five_sub_questions(self, mock_llm):
        from app.agent.nodes import decompose

        seven_questions = [f"q{i}" for i in range(7)]
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content=str(seven_questions).replace("'", '"'))
        )
        with patch("app.agent.nodes.get_llm", return_value=mock_llm):
            result = await decompose(make_state())

        assert len(result["sub_questions"]) == 5


# ---------------------------------------------------------------------------
# human_review
# ---------------------------------------------------------------------------


class TestHumanReview:
    async def test_interrupt_is_called_with_sub_questions(self):
        from app.agent.nodes import human_review

        sub_questions = ["q1", "q2", "q3"]
        state = make_state(sub_questions=sub_questions)

        with patch(
            "app.agent.nodes.interrupt", return_value=["edited_q1", "edited_q2"]
        ) as mock_interrupt:
            result = await human_review(state)

        mock_interrupt.assert_called_once()
        call_arg = mock_interrupt.call_args[0][0]
        assert call_arg["type"] == "human_review"
        assert call_arg["sub_questions"] == sub_questions

    async def test_returns_updated_questions_from_user(self):
        from app.agent.nodes import human_review

        with patch(
            "app.agent.nodes.interrupt", return_value=["new_q1", "new_q2"]
        ):
            result = await human_review(
                make_state(sub_questions=["orig_q1", "orig_q2"])
            )

        assert result["sub_questions"] == ["new_q1", "new_q2"]
        assert result["awaiting_user_input"] is False

    async def test_keeps_original_questions_if_no_list_returned(self):
        from app.agent.nodes import human_review

        with patch("app.agent.nodes.interrupt", return_value="ok"):
            result = await human_review(
                make_state(sub_questions=["orig_q1"])
            )

        assert result["sub_questions"] == ["orig_q1"]


# ---------------------------------------------------------------------------
# research
# ---------------------------------------------------------------------------


class TestResearch:
    async def test_routes_web_question_to_web_search(self, mock_llm):
        from app.agent.nodes import research

        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='["web"]'))
        with (
            patch("app.agent.nodes.get_llm", return_value=mock_llm),
            patch(
                "app.agent.nodes.web_search", return_value="Web result"
            ) as mock_web,
            patch("app.agent.nodes.finance_search", return_value="Finance result"),
        ):
            result = await research(make_state(sub_questions=["Latest AI news"]))

        mock_web.assert_called_once()
        assert result["research_results"][0]["tool_used"] == "web"
        assert result["research_results"][0]["result"] == "Web result"

    async def test_routes_finance_question_to_finance_search(self, mock_llm):
        from app.agent.nodes import research

        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='["finance"]'))
        with (
            patch("app.agent.nodes.get_llm", return_value=mock_llm),
            patch("app.agent.nodes.web_search", return_value="Web result"),
            patch(
                "app.agent.nodes.finance_search", return_value="$AAPL price data"
            ) as mock_fin,
        ):
            result = await research(
                make_state(sub_questions=["What is AAPL stock price?"])
            )

        mock_fin.assert_called_once()
        assert result["research_results"][0]["tool_used"] == "finance"

    async def test_tool_failure_recorded_not_raised(self, mock_llm):
        from app.agent.nodes import research

        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='["web"]'))
        with (
            patch("app.agent.nodes.get_llm", return_value=mock_llm),
            patch(
                "app.agent.nodes.web_search",
                side_effect=RuntimeError("Tavily down"),
            ),
        ):
            result = await research(make_state(sub_questions=["Any question"]))

        assert len(result["research_results"]) == 1
        assert "Tool error" in result["research_results"][0]["result"]

    async def test_multiple_sub_questions_all_researched(self, mock_llm):
        from app.agent.nodes import research

        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='["web", "web", "web"]'))
        with (
            patch("app.agent.nodes.get_llm", return_value=mock_llm),
            patch("app.agent.nodes.web_search", return_value="Result"),
        ):
            result = await research(
                make_state(sub_questions=["q1", "q2", "q3"])
            )

        assert len(result["research_results"]) == 3


# ---------------------------------------------------------------------------
# synthesize
# ---------------------------------------------------------------------------


class TestSynthesize:
    async def test_produces_final_answer(self, mock_llm):
        from app.agent.nodes import synthesize

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="AI will transform employment significantly.")
        )
        research_results: list[ResearchResult] = [
            {
                "sub_question": "How does AI affect jobs?",
                "tool_used": "web",
                "result": "AI is automating many tasks.",
            }
        ]
        state = make_state(
            query="Impact of AI on employment",
            research_results=research_results,
        )
        with patch("app.agent.nodes.get_llm", return_value=mock_llm):
            result = await synthesize(state)

        assert result["final_answer"] == "AI will transform employment significantly."
        assert result["current_node"] == "synthesize"

    async def test_includes_memory_context_in_prompt(self, mock_llm):
        from app.agent.nodes import synthesize

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="Synthesis answer")
        )
        state = make_state(
            memory_context="Past context: AI replaced factory jobs.",
            research_results=[
                {"sub_question": "q", "tool_used": "web", "result": "r"}
            ],
        )
        with patch("app.agent.nodes.get_llm", return_value=mock_llm) as _:
            await synthesize(state)

        # Verify the LLM was invoked (memory context will be embedded in the prompt)
        mock_llm.ainvoke.assert_called_once()


# ---------------------------------------------------------------------------
# save_memory
# ---------------------------------------------------------------------------


class TestSaveMemory:
    async def test_calls_sqlite_and_pinecone(self, mock_llm):
        from app.agent.nodes import save_memory

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="Summary of the research.")
        )
        state = make_state(
            final_answer="The final answer.",
            research_results=[
                {"sub_question": "q1", "tool_used": "web", "result": "r1"}
            ],
        )

        with (
            patch("app.agent.nodes.get_llm", return_value=mock_llm),
            patch(
                "app.memory.conversation_store.save_conversation", new_callable=AsyncMock
            ) as mock_save_conv,
            patch(
                "app.memory.conversation_store.save_message", new_callable=AsyncMock
            ) as mock_save_msg,
            patch(
                "app.memory.pinecone_client.upsert_chunks"
            ) as mock_upsert,
        ):
            result = await save_memory(state)

        assert mock_save_conv.called
        assert mock_save_msg.called
        mock_upsert.assert_called_once()
        assert result["current_node"] == "save_memory"

    async def test_sqlite_failure_is_non_fatal(self, mock_llm):
        from app.agent.nodes import save_memory

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="Summary.")
        )
        with (
            patch("app.agent.nodes.get_llm", return_value=mock_llm),
            patch(
                "app.memory.conversation_store.save_conversation",
                new_callable=AsyncMock,
                side_effect=Exception("DB locked"),
            ),
            patch("app.memory.pinecone_client.upsert_chunks"),
        ):
            # Should not raise
            result = await save_memory(make_state(final_answer="answer"))

        assert result["current_node"] == "save_memory"

    async def test_pinecone_failure_is_non_fatal(self, mock_llm):
        from app.agent.nodes import save_memory

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="Summary.")
        )
        with (
            patch("app.agent.nodes.get_llm", return_value=mock_llm),
            patch(
                "app.memory.conversation_store.save_conversation",
                new_callable=AsyncMock,
            ),
            patch(
                "app.memory.conversation_store.save_message",
                new_callable=AsyncMock,
            ),
            patch(
                "app.memory.pinecone_client.upsert_chunks",
                side_effect=Exception("Pinecone error"),
            ),
        ):
            result = await save_memory(make_state(final_answer="answer"))

        assert result["current_node"] == "save_memory"
