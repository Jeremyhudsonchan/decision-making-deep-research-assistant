"""
Tests for LangGraph routing logic and graph structure.
"""

import pytest
from app.agent.graph import _route_after_decompose, compiled_graph


def make_state(**overrides):
    base = {
        "query": "test",
        "sub_questions": ["q1"],
        "research_results": [],
        "final_answer": "",
        "interactive_mode": False,
        "awaiting_user_input": False,
        "user_clarification": None,
        "conversation_id": "test-conv",
        "messages": [],
        "memory_context": "",
        "current_node": "",
        "error": None,
    }
    base.update(overrides)
    return base


class TestRouteAfterDecompose:
    def test_interactive_mode_routes_to_human_review(self):
        state = make_state(interactive_mode=True)
        assert _route_after_decompose(state) == "human_review"

    def test_autonomous_mode_routes_to_research(self):
        state = make_state(interactive_mode=False)
        assert _route_after_decompose(state) == "research"

    def test_missing_interactive_mode_defaults_to_research(self):
        state = make_state()
        del state["interactive_mode"]
        assert _route_after_decompose(state) == "research"


class TestCompiledGraph:
    def test_all_six_nodes_registered(self):
        """Verify the graph was built with all expected node names."""
        expected_nodes = {
            "retrieve_memory",
            "decompose",
            "human_review",
            "research",
            "synthesize",
            "save_memory",
        }
        # compiled_graph.nodes is the dict of registered node names
        actual_nodes = set(compiled_graph.nodes.keys())
        assert expected_nodes.issubset(actual_nodes)

    def test_compiled_graph_is_not_none(self):
        assert compiled_graph is not None

    def test_graph_has_checkpointer(self):
        assert compiled_graph.checkpointer is not None
