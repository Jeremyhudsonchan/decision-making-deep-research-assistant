"""
LangGraph StateGraph for the research agent.

Flow:
  retrieve_memory → decompose → [human_review if interactive] → research → synthesize → save_memory

Interrupts:
  When interactive_mode=True, the graph is interrupted before "research"
  via the human_review node's interrupt() call.
  The caller resumes the graph with updated sub-questions.
"""

import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.state import AgentState
from app.agent.nodes import (
    retrieve_memory,
    decompose,
    human_review,
    research,
    synthesize,
    save_memory,
)

logger = logging.getLogger(__name__)

# In-memory checkpointer (sufficient for local-first; swap for SqliteSaver/PostgresSaver later)
checkpointer = MemorySaver()


def _route_after_decompose(state: AgentState) -> str:
    """Route to human_review if interactive mode is on, else go straight to research."""
    if state.get("interactive_mode", False):
        return "human_review"
    return "research"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("retrieve_memory", retrieve_memory)
    graph.add_node("decompose", decompose)
    graph.add_node("human_review", human_review)
    graph.add_node("research", research)
    graph.add_node("synthesize", synthesize)
    graph.add_node("save_memory", save_memory)

    # Entry
    graph.add_edge(START, "retrieve_memory")
    graph.add_edge("retrieve_memory", "decompose")

    # Conditional: interactive vs autonomous
    graph.add_conditional_edges(
        "decompose",
        _route_after_decompose,
        {
            "human_review": "human_review",
            "research": "research",
        },
    )

    # After human review, proceed to research
    graph.add_edge("human_review", "research")

    # Linear tail
    graph.add_edge("research", "synthesize")
    graph.add_edge("synthesize", "save_memory")
    graph.add_edge("save_memory", END)

    return graph


# Compile once at module load; all routes share this compiled graph
compiled_graph = build_graph().compile(checkpointer=checkpointer)
