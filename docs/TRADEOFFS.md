# Architecture Tradeoffs

This project is designed as a pragmatic local-first research assistant. The current architecture keeps the system small and easy to reason about, but that simplicity comes with tradeoffs that are worth making explicit.

## 1. Single backend process vs distributed coordination

The current implementation assumes a single FastAPI backend process is responsible for the full agent lifecycle.

### Why this is a good tradeoff now

- Easier to develop and debug locally
- No service-to-service coordination
- Streaming state and LangGraph execution are straightforward
- Fewer infrastructure dependencies for a prototype

### What it costs later

- In-memory checkpoints do not survive process restarts
- Horizontal scaling becomes harder because execution state is process-local
- Interactive sessions become more fragile once multiple app instances are involved

For local development, this is a reasonable tradeoff. For multi-user deployment, durable shared checkpointing becomes more important.

## 2. SQLite vs Postgres

SQLite is currently used for conversation history and basic persistence.

### Why this is a good tradeoff now

- Extremely simple setup
- Works well in Docker and local development
- No separate database service required
- Good fit for low-concurrency prototyping

### What it costs later

- Not ideal for concurrent multi-user write patterns
- Limited operational tooling compared to Postgres
- Less flexibility for richer relational data models, analytics, and background job metadata

SQLite is the right choice for a compact prototype. Postgres is the more natural next step once the system needs stronger concurrency, durability, and operational visibility.

## 3. Pinecone for semantic memory vs keeping memory fully local

The project uses Pinecone for semantic retrieval and SQLite for structured conversation history.

### Why this is a good tradeoff now

- Keeps semantic search concerns separate from transactional storage
- Makes it easy to retrieve prior relevant context for future questions
- Avoids building custom vector search infrastructure

### What it costs later

- Introduces an external dependency into the core research flow
- Requires more explicit thinking around namespaces, retrieval thresholds, and memory quality
- Can make local-only development less self-contained

This is a useful split for experimentation, but the memory strategy will likely need refinement as the dataset and user count grow.

## 4. SSE streaming vs more complex real-time infrastructure

The frontend consumes streamed backend updates over Server-Sent Events.

### Why this is a good tradeoff now

- Simple to implement for one-way backend-to-client updates
- Good fit for progressive research status updates
- Easier to reason about than introducing WebSockets too early

### What it costs later

- Less flexible for richer bidirectional real-time interactions
- Requires more care once there are proxies, reconnect behavior, and multiple runtime environments
- Background job progress can become more awkward if execution moves away from the request lifecycle

For the current product shape, SSE is a sensible choice. It should only be replaced if the interaction model becomes substantially more real-time and stateful.

## 5. LLM-based routing vs deterministic orchestration

The current agent uses the LLM to decompose questions and choose between the available tools.

### Why this is a good tradeoff now

- Fast to iterate on
- Flexible for ambiguous or broad research questions
- Keeps orchestration logic compact

### What it costs later

- Routing behavior can become inconsistent
- Debugging poor tool choices is harder than debugging deterministic rules
- Quality may vary depending on model behavior and prompt sensitivity

This is a good prototype pattern, but more deterministic routing or hybrid routing logic will likely improve reliability over time.

## 6. Autonomous mode vs interactive mode

One of the central product decisions in this repo is the toggle between autonomous and interactive execution.

### Why this is a good tradeoff now

- Supports both quick answers and human-in-the-loop review
- Makes the planning process visible when users care about it
- Keeps the interface simple while still allowing intervention

### What it costs later

- Interactive mode introduces more state management complexity
- Durable checkpoints become much more important
- UX complexity grows as the number of tools and planning steps increase

Even with those costs, this tradeoff feels worthwhile. The ability to inspect and adjust the agent's plan is one of the more valuable product ideas in the current system.

## Summary

The current architecture optimizes for clarity, iteration speed, and local-first development. That is a good bias for this stage of the project.

The main future-state shifts are fairly clear:

- Move from SQLite to Postgres
- Move from in-memory checkpoints to durable shared agent state
- Add queue-based background execution for longer-running research jobs
- Improve observability, retries, and tool orchestration

None of those require changing the core idea. They mostly involve making the current workflow more durable, scalable, and multi-user ready.
