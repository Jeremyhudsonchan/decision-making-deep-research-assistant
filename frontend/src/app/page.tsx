'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import ChatInput from '@/components/ChatInput'
import MessageList, { Message } from '@/components/MessageList'
import ModeToggle from '@/components/ModeToggle'
import ResearchProgress from '@/components/ResearchProgress'
import {
  startResearch,
  submitClarification,
  SSEEvent,
  ResearchResultSummary,
} from '@/lib/api'

type AppStatus = 'idle' | 'running' | 'awaiting_input' | 'completed' | 'error'

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([])
  const [interactive, setInteractive] = useState(false)
  const [status, setStatus] = useState<AppStatus>('idle')
  const [currentNode, setCurrentNode] = useState<string | null>(null)
  const [subQuestions, setSubQuestions] = useState<string[]>([])
  const [editableQuestions, setEditableQuestions] = useState<string[]>([])
  const [researchResults, setResearchResults] = useState<ResearchResultSummary[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)

  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when messages or progress updates
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, subQuestions, researchResults])

  const addMessage = useCallback((role: Message['role'], content: string) => {
    setMessages((prev) => [
      ...prev,
      { id: uuidv4(), role, content, timestamp: new Date() },
    ])
  }, [])

  const handleEvent = useCallback((event: SSEEvent) => {
    switch (event.type) {
      case 'start':
        setStatus('running')
        setCurrentNode(null)
        setSubQuestions([])
        setResearchResults([])
        if (event.conversation_id) setConversationId(event.conversation_id)
        break

      case 'node_start':
        setCurrentNode(event.node ?? null)
        break

      case 'node_end':
        setCurrentNode(null)
        break

      case 'sub_questions':
        setSubQuestions(event.sub_questions ?? [])
        setEditableQuestions(event.sub_questions ?? [])
        break

      case 'awaiting_input':
        setStatus('awaiting_input')
        setSubQuestions(event.sub_questions ?? [])
        setEditableQuestions(event.sub_questions ?? [])
        setCurrentNode('human_review')
        break

      case 'research_results':
        setResearchResults(event.results ?? [])
        break

      case 'final_answer':
        if (event.answer) {
          addMessage('assistant', event.answer)
        }
        break

      case 'completed':
        setStatus('completed')
        setCurrentNode(null)
        break

      case 'resume':
        setStatus('running')
        setCurrentNode('research')
        break

      case 'error':
        setStatus('error')
        addMessage('assistant', `Error: ${event.error ?? 'Unknown error'}`)
        setCurrentNode(null)
        break
    }
  }, [addMessage])

  const handleSubmit = useCallback(async (query: string) => {
    setStatus('running')
    setCurrentNode('retrieve_memory')
    setSubQuestions([])
    setResearchResults([])
    addMessage('user', query)

    const convId = conversationId ?? undefined

    const id = await startResearch({
      query,
      interactive_mode: interactive,
      conversation_id: convId,
      onEvent: handleEvent,
      onDone: () => {
        setStatus((s) => s === 'awaiting_input' ? s : 'idle')
        setCurrentNode(null)
      },
      onError: (err) => {
        setStatus('error')
        addMessage('assistant', `Connection error: ${err.message}`)
      },
    })

    if (id && !conversationId) {
      setConversationId(id)
    }
  }, [conversationId, interactive, handleEvent, addMessage])

  const handleAddQuestion = useCallback(() => {
    setEditableQuestions((prev) => [...prev, ''])
  }, [])

  const handleDeleteQuestion = useCallback((index: number) => {
    setEditableQuestions((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const handleApproveQuestions = useCallback(async () => {
    if (!conversationId) return
    setStatus('running')
    setCurrentNode(null)

    const filtered = editableQuestions.filter(q => q.trim() !== '')
    setSubQuestions(filtered)
    await submitClarification(
      conversationId,
      filtered,
      handleEvent,
      () => {
        setStatus((s) => (s === 'completed' || s === 'error') ? s : 'idle')
        setCurrentNode(null)
      },
      (err) => {
        setStatus('error')
        addMessage('assistant', `Error resuming: ${err.message}`)
      },
    )
  }, [conversationId, editableQuestions, handleEvent, addMessage])

  const isDisabled = status === 'running' || status === 'awaiting_input'
  const showProgress = status !== 'idle' || subQuestions.length > 0

  return (
    <div className="flex h-screen max-w-6xl mx-auto p-4 gap-4">
      {/* Left: chat column */}
      <div className="flex flex-col flex-1 min-w-0 gap-4">
        {/* Header */}
        <header className="flex items-center justify-between py-2 border-b border-slate-800">
          <div>
            <h1 className="text-lg font-bold text-slate-100">Deep Research Assistant</h1>
            <p className="text-xs text-slate-500">Powered by LangGraph · Tavily · Yahoo Finance</p>
          </div>
          <ModeToggle interactive={interactive} onChange={setInteractive} disabled={isDisabled} />
        </header>

        {/* Messages */}
        <MessageList messages={messages} />

        {/* Chat Input */}
        <ChatInput
          onSubmit={handleSubmit}
          disabled={isDisabled}
          placeholder={
            status === 'awaiting_input'
              ? 'Waiting for your approval in the sidebar...'
              : 'Ask a research question...'
          }
        />

        <div ref={bottomRef} />
      </div>

      {/* Right: sidebar — only rendered when showProgress */}
      {showProgress && (
        <aside className="w-80 flex flex-col gap-4 shrink-0 overflow-y-auto">
          <ResearchProgress
            subQuestions={subQuestions}
            results={researchResults}
            currentNode={currentNode}
            isAwaitingInput={status === 'awaiting_input'}
            editableQuestions={editableQuestions}
            onEditQuestion={(i, val) =>
              setEditableQuestions((prev) => prev.map((q, idx) => (idx === i ? val : q)))
            }
            onAddQuestion={handleAddQuestion}
            onDeleteQuestion={handleDeleteQuestion}
            onApproveQuestions={handleApproveQuestions}
          />
        </aside>
      )}
    </div>
  )
}
