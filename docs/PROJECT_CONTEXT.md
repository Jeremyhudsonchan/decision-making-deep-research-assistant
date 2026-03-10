# Why I Built This Project

This project started as a personal testing ground.

I wanted something more useful than a basic chat UI sitting on top of a model. A lot of the questions I care about are not one-shot questions. They usually need some decomposition, some retrieval, and some structure before the final answer is actually useful.

So one motivation was simple: I wanted to build a system that could actually answer my questions in a way that felt closer to a research assistant than a generic chatbot.

## Personal testing and experimentation

Part of the appeal of this project was being able to test ideas in a small environment that I could understand end-to-end.

I wanted to try things such as:

- breaking a question into sub-questions before researching it
- exposing the planning process instead of hiding it
- letting the user switch between autonomous and interactive modes
- storing prior context so future questions could benefit from earlier work

That made the repo useful as both a product experiment and an engineering sandbox.

## Using local models during development

Another reason for building it this way was to leave room for local model experimentation.

Even though the project supports hosted APIs, I also wanted the option to use a local model during development, especially for testing orchestration patterns and understanding where model quality actually matters. Using something like Qwen locally is useful here because it lets me experiment with prompts, routing, decomposition, and workflow design without always depending on an external hosted setup.

That does not mean local models remove all tradeoffs. In practice, they introduce a different set of questions around latency, quality, hardware constraints, and operational complexity. But that is part of what made the project interesting to build.

## Why I used a simple agent orchestrator

Another part of the project was deciding how much orchestration I actually needed.

I did not want to overcomplicate the system too early. A lot of agent projects become hard to reason about because they introduce too many moving parts at once: too many tools, too many routing branches, too many hidden behaviors, and too much framework abstraction before the core workflow is even clear.

So I deliberately kept the orchestrator simple.

The workflow is basically:

- retrieve context
- break the question into sub-questions
- optionally let the user review the plan
- research each sub-question
- synthesize the answer
- save the result

That was enough structure to make the assistant feel more capable than a single prompt, without making the system difficult to inspect or debug.

I also liked that a simple orchestrator made it easier to answer practical questions during development:

- where is the system making decisions?
- where should a user be able to intervene?
- what state needs to persist between steps?
- what parts should remain deterministic versus model-driven?

Using a lightweight orchestration approach helped keep those questions visible. It let me focus on the workflow itself instead of getting buried in framework complexity.

In other words, I was less interested in building the most sophisticated agent possible, and more interested in building an agent workflow that was understandable, adjustable, and useful.

## Learning through architecture tradeoffs

This project was also a way for me to learn more concretely about the tradeoffs involved in agent systems.

Once you move past a single prompt and start building a workflow, a different set of questions starts to matter:

- when should a system act autonomously versus ask for review?
- what should live in long-term memory versus short-term session state?
- when is a simple local-first architecture enough?
- what starts to break once you imagine more users or more concurrency?
- where should the design stay flexible for future changes?

Those questions were just as important to me as getting the application itself working.

## What I wanted out of it

At a practical level, I wanted a system that could:

- help me think through more complex questions
- make the planning process visible when needed
- give me a place to experiment with both hosted and local models
- teach me more about the product and infrastructure tradeoffs behind agent-style applications

So this repo is not only the implementation of a research assistant. It is also a record of the kinds of decisions that come up when trying to build one in a way that is inspectable, iterative, and useful.
