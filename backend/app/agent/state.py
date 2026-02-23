from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
import operator


class ResearchResult(TypedDict):
    sub_question: str
    tool_used: str  # "web" | "finance"
    result: str


class AgentState(TypedDict):
    # Core research fields
    query: str                              # Original user query
    sub_questions: list[str]               # Decomposed sub-questions
    research_results: list[ResearchResult]  # Results per sub-question
    final_answer: str                       # Synthesized answer

    # Mode control
    interactive_mode: bool                  # Human-in-the-loop flag
    awaiting_user_input: bool               # True when paused for user clarification
    user_clarification: Optional[str]       # User's response in interactive mode

    # Memory + tracking
    conversation_id: str
    messages: Annotated[list[BaseMessage], operator.add]  # LangChain message history
    memory_context: str                     # Retrieved Pinecone context prepended to prompts

    # Status tracking for streaming
    current_node: str
    error: Optional[str]
