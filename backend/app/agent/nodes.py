"""
LangGraph node implementations.

Nodes:
  retrieve_memory  → pull relevant Pinecone chunks
  decompose        → LLM breaks query into sub-questions
  human_review     → interrupt point for interactive mode
  research         → run tools per sub-question
  synthesize       → LLM produces final answer
  save_memory      → persist to SQLite + Pinecone
"""

import asyncio
import json
import logging
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.types import interrupt

from app.agent.state import AgentState, ResearchResult
from app.agent.llm import get_llm
from app.agent.tools.web_search import web_search
from app.agent.tools.yahoo_finance import finance_search
from app.memory import pinecone_client, conversation_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node: retrieve_memory
# ---------------------------------------------------------------------------


async def retrieve_memory(state: AgentState) -> dict:
    """Query Pinecone for relevant past context and prepend to state."""
    query = state["query"]
    logger.info(f"[retrieve_memory] Querying Pinecone for: {query[:80]}")

    try:
        results = pinecone_client.query_similar(query, top_k=5)
        if results:
            context_parts = [
                f"[Past context — relevance {r['score']:.2f}]\n{r['text']}"
                for r in results
                if r["score"] > 0.6  # Only include reasonably relevant chunks
            ]
            memory_context = "\n\n".join(context_parts)
        else:
            memory_context = ""
    except Exception as e:
        logger.warning(f"Memory retrieval failed (continuing without): {e}")
        memory_context = ""

    return {"memory_context": memory_context, "current_node": "retrieve_memory"}


# ---------------------------------------------------------------------------
# Node: decompose
# ---------------------------------------------------------------------------


async def decompose(state: AgentState) -> dict:
    """Use LLM to break the query into 3-5 focused sub-questions."""
    query = state["query"]
    memory_context = state.get("memory_context", "")

    system_prompt = (
        "You are a research planning assistant. Your job is to break down a complex "
        "research question into 3-5 focused sub-questions that, when answered together, "
        "will provide a comprehensive answer to the original question.\n\n"
        "Return ONLY a JSON array of strings, e.g.:\n"
        '["sub-question 1", "sub-question 2", "sub-question 3"]\n\n'
        "Do not include any other text or explanation."
    )

    user_content = f"Research question: {query}"
    if memory_context:
        user_content = f"Relevant past context:\n{memory_context}\n\n{user_content}"

    llm = get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]
    logger.debug("[decompose] LLM input messages:\n%s",
                 "\n---\n".join(m.content for m in messages))
    response = await llm.ainvoke(messages)
    logger.debug("[decompose] LLM output:\n%s", response.content)

    try:
        content = response.content.strip()
        # Strip markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        sub_questions = json.loads(content)
        if not isinstance(sub_questions, list) or not sub_questions:
            raise ValueError("Expected a non-empty list")
        sub_questions = [str(q) for q in sub_questions[:5]]
    except Exception as e:
        logger.warning(f"Failed to parse sub-questions JSON: {e}. Raw: {response.content[:200]}")
        # Fallback: treat the whole query as one sub-question
        sub_questions = [query]

    logger.info("[decompose] Sub-questions: %s", sub_questions)
    return {
        "sub_questions": sub_questions,
        "current_node": "decompose",
        "messages": [
            HumanMessage(content=query),
            AIMessage(content=f"Decomposed into sub-questions: {json.dumps(sub_questions)}"),
        ],
    }


# ---------------------------------------------------------------------------
# Node: human_review (interrupt)
# ---------------------------------------------------------------------------


async def human_review(state: AgentState) -> dict:
    """
    Pause execution in interactive mode.
    LangGraph's interrupt() suspends the graph and returns control to the caller.
    The caller (API route) will resume the graph with the user's edited sub-questions.
    """
    sub_questions = state["sub_questions"]
    logger.info("[human_review] Pausing for user review of sub-questions")

    # interrupt() raises a special exception that LangGraph catches to suspend the graph.
    # The value passed is what gets returned to the caller via the checkpoint.
    user_response = interrupt({
        "type": "human_review",
        "sub_questions": sub_questions,
        "message": "Please review and edit the sub-questions if needed, then continue.",
    })

    # When resumed, user_response contains the updated sub-questions
    if isinstance(user_response, list):
        updated_questions = [str(q) for q in user_response]
    else:
        updated_questions = sub_questions  # Keep original if no update

    return {
        "sub_questions": updated_questions,
        "awaiting_user_input": False,
        "current_node": "human_review",
    }


# ---------------------------------------------------------------------------
# Node: research
# ---------------------------------------------------------------------------


_TOOL_CLASSIFICATION_PROMPT = """You are a research tool router. For each sub-question, decide whether to use:
- "web": for general information, news, opinions, recent events, analysis
- "finance": for stock prices, company financials, market data (requires a ticker symbol)

Reply with ONLY a JSON array of strings, one entry per question, each "web" or "finance".
Example for 3 questions: ["web", "finance", "web"]
Do not include any other text."""


async def _classify_tools_batch(questions: list[str]) -> list[str]:
    """Classify all sub-questions in a single LLM call. Returns list of 'web'/'finance'."""
    numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    llm = get_llm()
    messages = [
        SystemMessage(content=_TOOL_CLASSIFICATION_PROMPT),
        HumanMessage(content=numbered),
    ]
    logger.debug("[research] LLM input messages:\n%s",
                 "\n---\n".join(m.content for m in messages))
    response = await llm.ainvoke(messages)
    logger.debug("[research] LLM output:\n%s", response.content)
    try:
        tools = json.loads(response.content.strip())
        if not isinstance(tools, list) or len(tools) != len(questions):
            raise ValueError("Length mismatch")
        return [t if t in ("web", "finance") else "web" for t in tools]
    except Exception:
        logger.warning("[research] Batch classify failed, defaulting all to 'web'")
        return ["web"] * len(questions)


async def _research_one(question: str, tool: str) -> ResearchResult:
    """Run the appropriate tool for a single sub-question, non-blocking."""
    logger.info(f"[research] Researching ({tool}): {question[:80]}")
    try:
        if tool == "finance":
            result_text = await asyncio.to_thread(finance_search, question)
        else:
            result_text = await asyncio.to_thread(web_search, question)
    except Exception as e:
        result_text = f"Tool error: {str(e)}"
    logger.info(f"[research] Done with '{question[:50]}' using {tool}")
    return ResearchResult(sub_question=question, tool_used=tool, result=result_text)


async def research(state: AgentState) -> dict:
    """Classify all sub-questions in one LLM call, then research them concurrently."""
    sub_questions = state["sub_questions"]
    logger.info(f"[research] Classifying {len(sub_questions)} sub-questions in one LLM call")
    tools = await _classify_tools_batch(sub_questions)
    logger.info(f"[research] Tool assignments: {list(zip([q[:30] for q in sub_questions], tools))}")
    results = await asyncio.gather(*[_research_one(q, t) for q, t in zip(sub_questions, tools)])
    return {"research_results": list(results), "current_node": "research"}


# ---------------------------------------------------------------------------
# Node: synthesize
# ---------------------------------------------------------------------------


async def synthesize(state: AgentState) -> dict:
    """Combine all research results into a final comprehensive answer."""
    query = state["query"]
    research_results = state["research_results"]
    memory_context = state.get("memory_context", "")

    # Build research summary
    research_text = "\n\n".join([
        f"Sub-question: {r['sub_question']}\n"
        f"Source: {r['tool_used'].upper()}\n"
        f"Findings:\n{r['result']}"
        for r in research_results
    ])

    system_prompt = (
        "You are a research synthesis expert. Given a research question and findings "
        "from multiple sources, synthesize a comprehensive, well-structured answer. "
        "Cite the sources of information where relevant. Be accurate and concise."
    )

    user_content = f"Original question: {query}\n\n"
    if memory_context:
        user_content += f"Relevant past context:\n{memory_context}\n\n"
    user_content += f"Research findings:\n{research_text}"

    llm = get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]
    logger.debug("[synthesize] LLM input messages:\n%s",
                 "\n---\n".join(m.content for m in messages))
    response = await llm.ainvoke(messages)
    logger.debug("[synthesize] LLM output:\n%s", response.content)

    final_answer = response.content
    logger.info(f"[synthesize] Generated answer ({len(final_answer)} chars)")

    return {
        "final_answer": final_answer,
        "current_node": "synthesize",
        "messages": [AIMessage(content=final_answer)],
    }


# ---------------------------------------------------------------------------
# Node: save_memory
# ---------------------------------------------------------------------------


async def save_memory(state: AgentState) -> dict:
    """Summarize and persist conversation to SQLite + Pinecone."""
    conversation_id = state["conversation_id"]
    query = state["query"]
    final_answer = state.get("final_answer", "")
    research_results = state.get("research_results", [])

    # Save messages to SQLite
    try:
        await conversation_store.save_conversation(conversation_id, query)
        await conversation_store.save_message(conversation_id, "user", query)
        await conversation_store.save_message(conversation_id, "assistant", final_answer)
    except Exception as e:
        logger.warning(f"SQLite save failed (non-fatal): {e}")

    # Generate a summary for Pinecone
    try:
        summary_text = f"Q: {query}\n\nA: {final_answer[:500]}"
        research_snippet = "\n".join([
            f"- {r['sub_question']}: {r['result'][:200]}"
            for r in research_results
        ])
        full_text = f"{summary_text}\n\nResearch details:\n{research_snippet}"

        # Generate a short summary via LLM for the metadata snippet
        llm = get_llm()
        summary_messages = [
            SystemMessage(content="Summarize the following research in 2-3 sentences."),
            HumanMessage(content=full_text[:2000]),
        ]
        logger.debug("[save_memory] LLM input messages:\n%s",
                     "\n---\n".join(m.content for m in summary_messages))
        summary_response = await llm.ainvoke(summary_messages)
        logger.debug("[save_memory] LLM output:\n%s", summary_response.content)
        summary = summary_response.content

        # Upsert to Pinecone
        pinecone_client.upsert_chunks(conversation_id, full_text, summary_snippet=summary)

        # Save summary back to SQLite
        await conversation_store.save_conversation(conversation_id, query, summary=summary)

    except Exception as e:
        logger.warning(f"Pinecone upsert failed (non-fatal): {e}")

    return {"current_node": "save_memory"}
