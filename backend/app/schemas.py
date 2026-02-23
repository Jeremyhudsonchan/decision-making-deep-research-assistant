from pydantic import BaseModel, Field
from typing import Optional
import uuid


class ResearchRequest(BaseModel):
    query: str = Field(..., description="The research question to answer", min_length=1)
    interactive_mode: bool = Field(
        default=False,
        description="If true, agent pauses after decomposition to allow user to review/edit sub-questions",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Continue an existing conversation. If None, a new conversation is started.",
    )


class ResearchResponse(BaseModel):
    conversation_id: str
    status: str = Field(description="One of: running, awaiting_input, completed, error")
    message: str = Field(description="Human-readable status message")


class ClarifyRequest(BaseModel):
    sub_questions: list[str] = Field(
        description="Edited or approved list of sub-questions from the user"
    )


class SubQuestion(BaseModel):
    question: str
    status: str = Field(default="pending", description="pending | researching | done")
    tool_used: Optional[str] = None
    result_snippet: Optional[str] = None


class ResearchStatus(BaseModel):
    conversation_id: str
    status: str
    query: str
    sub_questions: list[SubQuestion] = []
    final_answer: Optional[str] = None
    error: Optional[str] = None


class ResearchInvokeResponse(BaseModel):
    conversation_id: str
    status: str = Field(description="One of: awaiting_input, completed, error")
    sub_questions: list[str] = []
    final_answer: Optional[str] = None
    research_results: list[dict] = []
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
