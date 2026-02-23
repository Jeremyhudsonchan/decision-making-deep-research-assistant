# Decision Making Deep Research Assistant

An AI-powered deep research agent that decomposes complex questions into sub-questions, conducts multi-source research, and synthesizes comprehensive answers.

## Architecture

- **Backend**: FastAPI + LangGraph agent orchestration
- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS
- **LLM**: Configurable (Anthropic Claude or OpenAI GPT)
- **Tools**: Tavily web search + Yahoo Finance
- **Memory**: Pinecone (vector RAG) + SQLite (conversation history)

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+
- API keys: Anthropic/OpenAI, Tavily, Pinecone

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys, then move it to the backend directory
mv .env backend/.env
```

### 2. Run the backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Backend runs at http://localhost:8000

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:3000

### 4. Or use Docker Compose

```bash
docker-compose up --build
```

## Usage

1. Open http://localhost:3000
2. Toggle **Autonomous** / **Interactive** mode
   - **Autonomous**: Agent researches fully automatically
   - **Interactive**: Agent pauses after decomposition so you can review/edit sub-questions
3. Type a research question and press Enter

### Example queries

- "What is the current stock price of Apple and what are analysts saying about it?"
- "Compare the financial performance of Tesla and Ford in the past year"
- "What are the latest developments in quantum computing?"

## Project Structure

```
backend/
  app/
    main.py              # FastAPI entry point
    schemas.py           # Pydantic request/response models
    agent/
      graph.py           # LangGraph StateGraph
      nodes.py           # Graph nodes
      state.py           # AgentState TypedDict
      llm.py             # LLM factory (OpenAI / Anthropic)
      tools/
        web_search.py    # Tavily search
        yahoo_finance.py # yfinance wrapper
    memory/
      conversation_store.py  # SQLite CRUD
      pinecone_client.py     # Vector memory
    api/routes/
      research.py        # POST /research, POST /research/{id}/clarify
      health.py          # GET /health

frontend/
  src/
    app/page.tsx         # Main chat page
    components/
      ChatInput.tsx
      MessageList.tsx
      ResearchProgress.tsx
      ModeToggle.tsx
    lib/api.ts           # Fetch + SSE client
```

## Environment Variables

| Variable            | Description                         | Required                           |
| ------------------- | ----------------------------------- | ---------------------------------- |
| `LLM_PROVIDER`      | `openai` or `anthropic`             | Yes                                |
| `LLM_MODEL`         | Model ID (e.g. `claude-sonnet-4-6`) | Yes                                |
| `ANTHROPIC_API_KEY` | Anthropic API key                   | If using Anthropic                 |
| `OPENAI_API_KEY`    | OpenAI API key                      | If using OpenAI                    |
| `TAVILY_API_KEY`    | Tavily search API key               | Yes                                |
| `PINECONE_API_KEY`  | Pinecone API key                    | Yes                                |
| `PINECONE_INDEX`    | Pinecone index name                 | Yes                                |
| `SQLITE_DB_PATH`    | Path to SQLite DB file              | No (default: `./data/research.db`) |
