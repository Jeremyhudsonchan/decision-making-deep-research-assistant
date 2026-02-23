# Decision Making Deep Research Assistant — Technical Documentation

## 1. Overview

This system is an AI-powered deep research assistant that takes complex user questions, automatically decomposes them into focused sub-questions, conducts multi-source research using specialized tools, and synthesizes a comprehensive answer. It supports two operating modes:

- **Autonomous mode** — the full research pipeline runs end-to-end without human intervention.
- **Interactive (human-in-the-loop) mode** — the agent pauses after decomposing the query so the user can review and edit sub-questions before research begins.

---

## 2. Architecture Diagram (ASCII)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              User / Client                                    │
│                                                                               │
│  POST /research  ──────►  SSE stream (text/event-stream)                     │
│  POST /research/invoke ►  JSON response (blocking)                           │
│  POST /research/{id}/clarify  ──►  SSE stream (resume)                       │
│  POST /research/{id}/clarify/invoke  ──►  JSON response                      │
│  GET  /research/{id}/status  ──►  JSON polling fallback                      │
└──────────────────────────────┬───────────────────────────────────────────────┘
                                │
                     ┌──────────▼──────────┐
                     │    FastAPI App       │
                     │   (main.py)          │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │  LangGraph Agent    │
                     │  (StateGraph)       │
                     └──────────┬──────────┘
                                │
          ┌─────────────────────▼─────────────────────────┐
          │                  Node Pipeline                  │
          │                                                 │
          │  retrieve_memory ──► decompose ──► [branch]    │
          │                           │                     │
          │               ┌───────────┴──────────┐         │
          │         interactive?                  │         │
          │              YES                     NO         │
          │               │                      │         │
          │        human_review         ──► research        │
          │               │                      │         │
          │               └──────────────────────┘         │
          │                            │                    │
          │                       synthesize                │
          │                            │                    │
          │                       save_memory               │
          └────────────────────────────────────────────────┘
                     │                        │
           ┌─────────▼──────┐      ┌──────────▼─────────┐
           │   Tools Layer  │      │   Memory Layer      │
           │                │      │                     │
           │  Tavily (web)  │      │  Pinecone (vector)  │
           │  yfinance      │      │  SQLite (history)   │
           └────────────────┘      └─────────────────────┘
```

---

## 3. Quick Start

### Local Development

**Backend** (from `backend/`):

```bash
# Install dependencies (first time)
uv sync

# Start the server (hot-reload)
uv run uvicorn app.main:app --reload
```

API available at: `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs`

**Frontend** (from `frontend/`):

```bash
npm install
npm run dev
```

UI available at: `http://localhost:3000`

### Docker Compose (both services)

```bash
# 1. Copy and fill in API keys
cp .env.example .env

# 2. Build and start
docker-compose up --build
```

---

## 4. Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes (if Anthropic) | — | API key for Claude models |
| `OPENAI_API_KEY` | Yes (if OpenAI or embeddings) | — | API key for GPT models and embeddings |
| `TAVILY_API_KEY` | Yes | — | API key for Tavily web search |
| `PINECONE_API_KEY` | Yes | — | API key for Pinecone vector store |
| `LLM_PROVIDER` | No | `anthropic` | LLM backend: `anthropic` or `openai` |
| `LLM_MODEL` | No | `claude-sonnet-4-6` | Model ID (e.g. `gpt-4o`, `claude-opus-4-6`) |
| `PINECONE_INDEX` | No | `research-memory` | Pinecone index name |
| `SQLITE_DB_PATH` | No | `./data/research.db` | Path to the SQLite database file |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated list of allowed CORS origins |

**Never hardcode a model or provider.** All agent code imports `get_llm()` from `app.agent.llm`.

---

## 5. Backend

### 5.1 FastAPI App (`main.py`)

Entry point for the backend. Responsibilities:

- Registers the `lifespan` context manager which calls `init_db()` on startup to initialize SQLite tables.
- Configures CORS middleware (origins from `CORS_ORIGINS` env var).
- Includes routers: `health.router` at `/`, `research.router` at `/research`.
- Validates critical env vars at startup (warns if missing, does not crash).

#### CORS `expose_headers` requirement

`CORSMiddleware` is configured with `expose_headers=["X-Conversation-Id"]`. This is distinct from `allow_headers=["*"]`:

- **`allow_headers`**: Controls which *request* headers the browser is permitted to include when making a cross-origin request (e.g. `Content-Type`, `Authorization`).
- **`expose_headers`**: Controls which *response* headers the browser's JavaScript is allowed to read via `response.headers.get(...)`.

Custom response headers (any header that isn't in the CORS "safe list" of `Cache-Control`, `Content-Language`, `Content-Type`, `Expires`, `Last-Modified`, `Pragma`) are blocked from JS unless explicitly listed in `expose_headers`. Without this, `response.headers.get('X-Conversation-Id')` always returns `null` in the browser even though the server sends the header, and the interactive mode's "Approve & Continue" button silently exits because `conversationId` is never set in React state.

### 5.2 Data Models (`schemas.py`)

All request/response shapes are Pydantic models:

| Model | Purpose |
|-------|---------|
| `ResearchRequest` | Input for starting research (`query`, `interactive_mode`, optional `conversation_id`) |
| `ResearchResponse` | Immediate response for SSE endpoints (`conversation_id`, `status`, `message`) |
| `ClarifyRequest` | Body for interactive resume (`sub_questions: list[str]`) |
| `SubQuestion` | Tracks per-question status in the status endpoint |
| `ResearchStatus` | Polling response (`conversation_id`, `status`, `query`, `final_answer`) |
| `ResearchInvokeResponse` | Non-streaming response (`status`, `final_answer`, `research_results`, `error`) |
| `HealthResponse` | Health check (`status: "ok"`, `version`) |

### 5.3 LLM Factory (`agent/llm.py`)

```python
@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel: ...
```

- Reads `LLM_PROVIDER` and `LLM_MODEL` from the environment.
- Supports `anthropic` (returns `ChatAnthropic`) and `openai` (returns `ChatOpenAI`).
- Both are initialized with `temperature=0` for deterministic outputs.
- The result is cached with `@lru_cache` — the same instance is reused for the process lifetime. In tests, call `get_llm.cache_clear()` before patching.
- Raises `ValueError` if the provider is unsupported or the API key is missing.

### 5.4 Agent State (`agent/state.py`)

`AgentState` is a `TypedDict` passed through the LangGraph pipeline. All nodes read from and write to it:

| Field | Type | Description |
|-------|------|-------------|
| `query` | `str` | Original user query |
| `sub_questions` | `list[str]` | Decomposed sub-questions (3–5) |
| `research_results` | `list[ResearchResult]` | Per-sub-question results with tool used |
| `final_answer` | `str` | Synthesized answer |
| `interactive_mode` | `bool` | If true, pause at `human_review` |
| `awaiting_user_input` | `bool` | True when interrupted |
| `user_clarification` | `Optional[str]` | User's edited sub-questions |
| `conversation_id` | `str` | UUID identifying the session |
| `messages` | `Annotated[list[BaseMessage], operator.add]` | LangChain message history (append-only) |
| `memory_context` | `str` | Retrieved Pinecone context prepended to prompts |
| `current_node` | `str` | Name of the last-executed node |
| `error` | `Optional[str]` | Error message if something failed |

`ResearchResult` is a `TypedDict` with `sub_question`, `tool_used`, and `result` fields.

### 5.5 LangGraph Graph (`agent/graph.py`)

```
retrieve_memory → decompose → [_route_after_decompose] → research → synthesize → save_memory
                                        ↓ (interactive)
                                   human_review → research
```

Key details:

- **`build_graph()`** constructs the `StateGraph` with 6 nodes and the conditional edge.
- **`_route_after_decompose(state)`** is the routing function: returns `"human_review"` if `interactive_mode=True`, else `"research"`.
- **`compiled_graph`** is compiled once at module load with a `MemorySaver` checkpointer. All API routes share this singleton.
- **`checkpointer = MemorySaver()`** holds in-memory state per `thread_id` (conversation ID). Thread IDs are passed via `config = {"configurable": {"thread_id": conversation_id}}`.

**Node registration table:**

| Node name | Function | Registered edge |
|-----------|----------|----------------|
| `retrieve_memory` | Pull past Pinecone context | START → retrieve_memory → decompose |
| `decompose` | Split query into sub-questions | → conditional edge |
| `human_review` | Interrupt for user review | → research |
| `research` | Run tools per sub-question | → synthesize |
| `synthesize` | Combine results into answer | → save_memory |
| `save_memory` | Persist to SQLite + Pinecone | → END |

### 5.6 Agent Nodes (`agent/nodes.py`)

#### `retrieve_memory(state)`

- **Purpose**: Query Pinecone for past research context relevant to the current query.
- **Inputs**: `state["query"]`
- **Outputs**: `{"memory_context": str, "current_node": "retrieve_memory"}`
- **Error handling**: Exceptions from Pinecone are caught and logged; returns `memory_context=""` (non-fatal).
- **Filtering**: Only chunks with `score > 0.6` are included.

#### `decompose(state)`

- **Purpose**: Use the LLM to break the query into 3–5 focused sub-questions.
- **Inputs**: `state["query"]`, `state["memory_context"]`
- **Outputs**: `{"sub_questions": list[str], "current_node": "decompose", "messages": [...]}`
- **Parsing**: Expects a JSON array. Strips markdown code fences if present. Truncates to 5 items.
- **Fallback**: If JSON parsing fails, returns `[original_query]` as the single sub-question.

#### `human_review(state)`

- **Purpose**: Pause the graph so the user can review/edit sub-questions (interactive mode only).
- **Inputs**: `state["sub_questions"]`
- **Outputs**: `{"sub_questions": list[str], "awaiting_user_input": False, "current_node": "human_review"}`
- **Mechanism**: Calls `langgraph.types.interrupt()` which suspends the graph at the checkpoint. The API route resumes it via `Command(resume=sub_questions)`.
- **Resume logic**: If the resumed value is a list, it replaces sub_questions; otherwise the original list is kept.

#### `research(state)`

- **Purpose**: For each sub-question, classify the appropriate tool and fetch results.
- **Inputs**: `state["sub_questions"]`
- **Outputs**: `{"research_results": list[ResearchResult], "current_node": "research"}`
- **Tool routing**: Calls `_classify_tool()` which asks the LLM to return `"web"` or `"finance"`. Defaults to `"web"` if response is unexpected.
- **Error handling**: Tool exceptions are caught; the error string is stored in `result` (the graph does not crash).

#### `synthesize(state)`

- **Purpose**: Combine all research results into a final, well-structured answer.
- **Inputs**: `state["query"]`, `state["research_results"]`, `state["memory_context"]`
- **Outputs**: `{"final_answer": str, "current_node": "synthesize", "messages": [AIMessage(...)]}`
- **Prompt**: System prompt instructs the LLM to cite sources and be concise.

#### `save_memory(state)`

- **Purpose**: Persist the conversation to SQLite and upsert a summary to Pinecone.
- **Inputs**: `state["conversation_id"]`, `state["query"]`, `state["final_answer"]`, `state["research_results"]`
- **Outputs**: `{"current_node": "save_memory"}`
- **SQLite**: Calls `save_conversation()` and `save_message()` for user and assistant turns.
- **Pinecone**: Generates a 2–3 sentence LLM summary, then calls `upsert_chunks()` with the full research text + summary.
- **Error handling**: Both SQLite and Pinecone failures are caught and logged (non-fatal). The final answer is always returned regardless of persistence success.

### 5.7 Research Tools

#### Web Search (`tools/web_search.py`)

Wraps the [Tavily](https://tavily.com) search API.

```python
def web_search(query: str, max_results: int = 5) -> str
```

- Requires `TAVILY_API_KEY` env var; returns an error string if missing.
- Calls `TavilyClient.search()` with `search_depth="advanced"` and `include_answer=True`.
- Output format: Tavily's auto-generated answer (if any) followed by numbered results with title, URL, and snippet (truncated to 800 chars).
- Returns `"No results found."` for empty responses.
- Exceptions are caught and returned as error strings (non-fatal to the pipeline).

#### Finance Search (`tools/yahoo_finance.py`)

Wraps [yfinance](https://github.com/ranaroussi/yfinance) for real-time market data.

```python
def finance_search(query: str) -> str
def get_stock_price(ticker: str) -> str
def get_company_info(ticker: str) -> str
def get_financials(ticker: str) -> str
def _extract_ticker(text: str) -> Optional[str]
```

**Ticker extraction heuristic** (`_extract_ticker`):

Attempts three regex patterns in order:
1. `$AAPL` — dollar-sign prefix
2. `AAPL)` — uppercase word followed by closing paren
3. `(AAPL)` — uppercase word wrapped in parens

Falls back to finding any 1–5 char uppercase word not in a common-word exclusion set (`I`, `A`, `THE`, `AND`, `OR`, `FOR`, `OF`, `IN`, `IS`, `IT`, `BE`).

**Routing rules in `finance_search`**:

| Trigger keywords | Function called |
|-----------------|----------------|
| Always | `get_stock_price(ticker)` |
| "about", "what is", "company", "business", "analyst", "sector", "industry" | `get_company_info(ticker)` |
| "revenue", "profit", "earning", "financial", "income", "cash flow", "debt", "margin" | `get_financials(ticker)` |

Returns an informative error string if no ticker can be extracted.

### 5.8 Memory Layer

#### Pinecone (`memory/pinecone_client.py`)

Stores conversation summaries as vector embeddings for RAG retrieval.

**Configuration:**

| Setting | Value |
|---------|-------|
| Index name | `research-memory` (or `PINECONE_INDEX` env var) |
| Embedding model | Pinecone integrated `llama-text-embed-v2` |
| Distance metric | Cosine (managed by Pinecone) |
| Field map | Records must contain a `content` field — that is the field embedded |
| Cloud | AWS `us-east-1` (serverless) |

**Integrated embeddings**: Records are stored with a `content` field. The Pinecone index is created with `embed.model="llama-text-embed-v2"` and `embed.fieldMap={"text": "content"}`, which means Pinecone handles embedding server-side at upsert and query time. No external embedding API call is made by this application.

**Chunking**: Character-level with `chunk_size=500`, `overlap=50`.

**Chunk metadata stored**: `conversation_id`, `chunk_index`, `text`, `summary_snippet`, `timestamp`.

**Scoring threshold**: Only chunks with `score > 0.6` are included in `memory_context` (set in `retrieve_memory` node).

**Lazy initialization**: The Pinecone client is initialized on first use (not at import time).

**Key functions:**

| Function | Description |
|----------|-------------|
| `upsert_chunks(conversation_id, text, summary_snippet)` | Chunk, embed, and upsert to Pinecone |
| `query_similar(query, top_k=5)` | Embed query and return top-k matches with score and text |

Both functions are wrapped in try/except — failures log a warning and return gracefully.

#### SQLite (`memory/conversation_store.py`)

Stores structured conversation history for the status/polling endpoint.

**Schema:**

```
Conversation
  id          TEXT  PRIMARY KEY  (UUID)
  query       TEXT               (original user query)
  summary     TEXT               (optional LLM-generated summary)
  created_at  DATETIME
  updated_at  DATETIME

Message
  id              INTEGER  PRIMARY KEY  AUTOINCREMENT
  conversation_id TEXT     FOREIGN KEY → Conversation.id  (indexed)
  role            TEXT     ("user" | "assistant" | "tool")
  content         TEXT
  timestamp       DATETIME
```

**Async driver**: `aiosqlite` via `sqlalchemy.ext.asyncio`.

**CRUD functions:**

| Function | Description |
|----------|-------------|
| `init_db()` | Create tables (idempotent) |
| `save_conversation(id, query, summary)` | Insert or update a Conversation record |
| `save_message(conversation_id, role, content)` | Append a Message record |
| `get_conversation(conversation_id)` | Fetch a Conversation by ID |
| `get_conversation_history(conversation_id)` | Fetch all Messages ordered by timestamp |

### 5.9 API Routes

Full endpoint reference:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns `{"status":"ok","version":"0.1.0"}` |
| `POST` | `/research` | Start research (SSE stream) |
| `POST` | `/research/invoke` | Start research (blocking JSON) |
| `POST` | `/research/{id}/clarify` | Resume interactive session (SSE stream) |
| `POST` | `/research/{id}/clarify/invoke` | Resume interactive session (blocking JSON) |
| `GET` | `/research/{id}/status` | Poll current status (returns 404 if not found) |

**SSE Event Contract:**

| Event type | Payload fields | Meaning |
|------------|----------------|---------|
| `start` | `conversation_id`, `status` | Stream started |
| `node_start` | `node` | A graph node began executing |
| `node_end` | `node` | A graph node finished executing |
| `sub_questions` | `sub_questions: string[]` | Decomposition complete |
| `awaiting_input` | `sub_questions`, `message` | Interactive pause — show edit UI |
| `research_results` | `results: [{sub_question, tool_used, snippet}]` | Research done |
| `final_answer` | `answer: string` | Synthesized answer ready |
| `completed` | `conversation_id`, `status` | All done |
| `resume` | `conversation_id`, `sub_questions` | Interactive session resumed |
| `error` | `error: string` | Something failed |

**Non-streaming (`/invoke`) response fields:**

```json
{
  "conversation_id": "uuid",
  "status": "completed | awaiting_input | error",
  "sub_questions": [],
  "final_answer": "...",
  "research_results": [{"sub_question": "...", "tool_used": "web", "snippet": "..."}],
  "error": null
}
```

---

## 6. Frontend

### 6.1 Page State Machine (`src/app/page.tsx`)

The main page manages a `status` state that drives the UI:

```
idle → researching → awaiting_input → researching → completed
                                                   ↘ error
```

| Status | Trigger | UI shown |
|--------|---------|----------|
| `idle` | Initial / after reset | Input form |
| `researching` | POST /research submitted | Progress tracker with live node updates |
| `awaiting_input` | `awaiting_input` SSE event received | Sub-question editor |
| `completed` | `completed` SSE event received | Final answer rendered as Markdown |
| `error` | `error` SSE event received | Error message |

#### `conversationId` — Dual-Source Population

`conversationId` (`useState<string | null>`) is the session identifier used by `handleApproveQuestions` to POST to `/research/{id}/clarify`. It is populated from **two places**:

1. **HTTP response header (primary)** — `startResearch()` in `api.ts` reads `response.headers.get('X-Conversation-Id')` from the `/research` POST response. This works because `CORSMiddleware` lists `X-Conversation-Id` in `expose_headers`. The return value of `startResearch()` is the conversation ID, and `handleSubmit` calls `setConversationId(id)`.

2. **`start` SSE event (defensive fallback)** — The first SSE event emitted by the backend is `{"type": "start", "conversation_id": "<uuid>", "status": "running"}`. The `handleEvent` switch case for `'start'` includes: `if (event.conversation_id) setConversationId(event.conversation_id)`. This ensures `conversationId` is set even if the HTTP header read fails (e.g. in some proxy or environment configurations).

Both paths call the same stable `setConversationId` setter, so double-setting is idempotent.

#### Interactive Mode — Sub-Question State Sync

When `handleApproveQuestions` runs, it must synchronize two separate pieces of state before calling `submitClarification`:

1. **`editableQuestions`** — the user's current edits (filtered to non-empty). This is what gets sent to the backend as `request.sub_questions`.
2. **`subQuestions`** — the state that drives the read-only progress sidebar (the question cards with pending/researching/done status icons).

`handleApproveQuestions` calls `setSubQuestions(filtered)` before `await submitClarification(...)`. Without this sync:
- The `research_results` SSE event returns objects with `sub_question` values matching the **edited** questions.
- The progress sidebar's `questionStates` array is built by `subQuestions.map(q => results.find(r => r.sub_question === q))`.
- If `subQuestions` still holds the original LLM-decomposed list, the `find()` calls fail for any edited question — deleted questions show permanently as "pending" and added questions produce no visible progress row.

### 6.2 SSE Client (`src/lib/api.ts`)

The SSE stream is consumed using `fetch()` + `ReadableStream` (not `EventSource`) because the initial request is a `POST`:

```typescript
async function* consumeSSEStream(response: Response): AsyncGenerator<SSEEvent>
```

The function reads the response body as a stream, splits on `\n\n`, parses each `data: ...` line as JSON, and yields typed event objects.

Key exports:

| Function | Description |
|----------|-------------|
| `startResearch(req)` | POST /research, returns a fetch Response for streaming |
| `invokeResearch(req)` | POST /research/invoke, returns JSON |
| `submitClarification(id, subQuestions)` | POST /research/{id}/clarify, returns a Response for streaming |
| `invokeClarity(id, subQuestions)` | POST /research/{id}/clarify/invoke, returns JSON |
| `getStatus(id)` | GET /research/{id}/status, returns JSON |

### 6.3 Components

| Component | File | Purpose |
|-----------|------|---------|
| `ChatInput` | `components/ChatInput.tsx` | Textarea with Enter-to-submit. Shift+Enter for newline. |
| `MessageList` | `components/MessageList.tsx` | Scrollable conversation history with Markdown rendering |
| `ResearchProgress` | `components/ResearchProgress.tsx` | Live sub-question tracker; switches to edit UI in interactive mode |
| `ModeToggle` | `components/ModeToggle.tsx` | Toggle between Autonomous and Interactive mode |

---

## 7. Key Architecture Decisions

1. **LangGraph `StateGraph` over custom orchestration**: LangGraph provides built-in checkpointing, conditional routing, and the `interrupt()` primitive for human-in-the-loop — avoiding hundreds of lines of custom graph traversal code.

2. **`MemorySaver` checkpointer (in-memory)**: Sufficient for local-first use. The checkpointer can be swapped for `SqliteSaver` or `PostgresSaver` in production without changing any node code.

3. **`interrupt()` for interactive mode**: LangGraph's `interrupt()` is the canonical way to pause a graph mid-execution and return control to the caller. The graph is resumed by calling `compiled_graph.ainvoke(Command(resume=value), config=config)`.

4. **SSE via `fetch()` + `ReadableStream` (not `EventSource`)**: `EventSource` only supports `GET` requests. Since research initiation is a `POST`, the frontend uses the Fetch API with a streaming response body.

5. **Non-fatal memory operations**: Both Pinecone and SQLite failures are wrapped in `try/except` and log a warning. The agent always returns a research answer even if persistence fails — correctness over durability.

6. **Compiled graph singleton**: `compiled_graph` is created once at module import in `graph.py` and shared across all API requests. This is safe because LangGraph's checkpointer isolates state per `thread_id`.

7. **LLM factory with `@lru_cache`**: `get_llm()` is cached so the same LangChain model instance is reused. All nodes import `get_llm()` rather than directly instantiating models, making the LLM provider fully configurable via env vars.

8. **Tool classification by LLM**: Rather than using keyword rules, the `research` node asks the LLM to classify each sub-question as `"web"` or `"finance"`. This is more robust for ambiguous queries but adds one LLM call per sub-question.

9. **Programmatic (non-streaming) endpoints (`/invoke`)**: The `/research/invoke` and `/research/{id}/clarify/invoke` endpoints expose the same research pipeline as blocking JSON responses. This makes the API testable and usable by non-browser clients without SSE handling.

10. **Pinecone scoring threshold (0.6)**: Only chunks with cosine similarity > 0.6 are included in `memory_context`. This prevents low-relevance past context from polluting new research prompts.

11. **CORS `expose_headers` for custom response headers**: Any HTTP response header outside the CORS safe list (`Cache-Control`, `Content-Language`, `Content-Type`, `Expires`, `Last-Modified`, `Pragma`) must be explicitly listed in `expose_headers` for browser JavaScript to be able to read it. `X-Conversation-Id` is a custom header carrying the session UUID — it is sent on the `/research` POST response and read by the frontend SSE client to initialize `conversationId` state. Omitting `expose_headers` breaks interactive mode silently.

12. **Dual-source `conversationId` (defensive SSE fallback)**: The `conversationId` React state is populated from both the HTTP response header (via `api.ts`) and the first SSE event's `conversation_id` payload (via `handleEvent`). If one path fails — e.g. the header is blocked — the stream still delivers the ID in the `start` event. This defense-in-depth approach ensures interactive mode works in environments with non-standard CORS behavior or proxy stripping.

13. **Sub-question state sync at approval time**: The frontend maintains two parallel lists — `subQuestions` (read-only progress display, sourced from SSE events) and `editableQuestions` (user-editable copy shown in interactive mode). They diverge when the user adds, deletes, or edits questions. At approval time, `handleApproveQuestions` explicitly syncs them by calling `setSubQuestions(filtered)` before submitting to the backend. This ensures the post-approval progress sidebar renders correct question rows and correctly maps incoming `research_results` to visible progress items.

---

## 8. Running Tests

```bash
cd backend

# Install all dependencies including dev
uv sync

# Run all tests
uv run pytest -v

# Run a specific module
uv run pytest tests/test_api/ -v
uv run pytest tests/test_agent/ -v
uv run pytest tests/test_tools/ -v
uv run pytest tests/test_memory/ -v

# Run with short traceback on failure
uv run pytest --tb=short
```

**Test structure:**

```
backend/tests/
├── conftest.py                          # Shared fixtures (env_vars, mock_llm, async_client)
├── test_schemas.py                      # Pydantic model validation
├── test_agent/
│   ├── test_nodes.py                    # Unit tests for each of the 6 node functions
│   └── test_graph_routing.py            # Routing function + graph structure
├── test_tools/
│   ├── test_web_search.py               # Tavily wrapper (mocked)
│   └── test_yahoo_finance.py            # yfinance wrapper (mocked)
├── test_memory/
│   └── test_conversation_store.py       # SQLite CRUD with temp-file DB per test
└── test_api/
    └── test_research_routes.py          # FastAPI route integration tests
```

**Key mocking patterns:**

```python
# Mock the LLM (used in node tests)
with patch("app.agent.nodes.get_llm", return_value=mock_llm):
    result = await decompose(state)

# Mock an async generator (used for SSE route tests)
async def fake_astream_events(*args, **kwargs):
    for event in FAKE_EVENTS:
        yield event
mocker.patch.object(compiled_graph, "astream_events", new=fake_astream_events)

# Mock Pinecone (non-fatal path)
with patch("app.memory.pinecone_client.query_similar", side_effect=Exception("down")):
    result = await retrieve_memory(state)
assert result["memory_context"] == ""
```

No real API calls are made in any test — all external services (LLM, Tavily, yfinance, Pinecone, SQLite) are mocked or use isolated temp databases.

---

## 9. Extending the System

### Adding a New Node

1. Implement the node function in `backend/app/agent/nodes.py`:

```python
async def my_new_node(state: AgentState) -> dict:
    # Read from state
    query = state["query"]
    # ... do work ...
    return {"some_field": value, "current_node": "my_new_node"}
```

2. Register the node and add edges in `backend/app/agent/graph.py`:

```python
graph.add_node("my_new_node", my_new_node)
graph.add_edge("synthesize", "my_new_node")   # example: insert before save_memory
graph.add_edge("my_new_node", "save_memory")
```

3. If the node produces output that should be streamed to the frontend, add a case in `_stream_research()` in `research.py`:

```python
elif kind == "on_chain_end" and name == "my_new_node":
    yield _sse_event("my_event_type", {"data": output.get("some_field")})
```

4. Add a field to `AgentState` in `state.py` if the node produces new state.

5. Write tests in `tests/test_agent/test_nodes.py`.

### Adding a New Tool

1. Create a new file in `backend/app/agent/tools/`:

```python
# tools/my_tool.py
def my_tool(query: str) -> str:
    """Returns a string result suitable for LLM prompts."""
    ...
```

2. Import and call it in the `research` node in `nodes.py`:

```python
from app.agent.tools.my_tool import my_tool

# In research():
if tool == "my_tool":
    result_text = my_tool(question)
```

3. Update the `_TOOL_CLASSIFICATION_PROMPT` to include the new tool option and its use case.

4. Write tests in `tests/test_tools/test_my_tool.py` with the external dependency mocked.
