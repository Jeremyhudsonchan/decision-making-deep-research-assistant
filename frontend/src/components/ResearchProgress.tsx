'use client'

import { useState } from 'react'
import { ResearchResultSummary } from '@/lib/api'

interface SubQuestionState {
  question: string
  status: 'pending' | 'researching' | 'done'
  toolUsed?: string
  snippet?: string
}

interface ResearchProgressProps {
  subQuestions: string[]
  results: ResearchResultSummary[]
  currentNode: string | null
  isAwaitingInput: boolean
  editableQuestions: string[]
  onEditQuestion: (index: number, value: string) => void
  onAddQuestion: () => void
  onDeleteQuestion: (index: number) => void
  onApproveQuestions: () => void
}

const NODE_LABELS: Record<string, string> = {
  retrieve_memory: 'Retrieving memory...',
  decompose: 'Breaking down question...',
  human_review: 'Waiting for your input...',
  research: 'Researching...',
  synthesize: 'Synthesizing answer...',
  save_memory: 'Saving to memory...',
}

const TOOL_BADGES: Record<string, { label: string; className: string }> = {
  web: { label: 'Web', className: 'bg-blue-900/60 text-blue-300 border border-blue-700' },
  finance: { label: 'Finance', className: 'bg-green-900/60 text-green-300 border border-green-700' },
}

export default function ResearchProgress({
  subQuestions,
  results,
  currentNode,
  isAwaitingInput,
  editableQuestions,
  onEditQuestion,
  onAddQuestion,
  onDeleteQuestion,
  onApproveQuestions,
}: ResearchProgressProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  if (!currentNode && subQuestions.length === 0) return null

  // Build per-question state
  const questionStates: SubQuestionState[] = subQuestions.map((q) => {
    const result = results.find((r) => r.sub_question === q)
    return {
      question: q,
      status: result ? 'done' : currentNode === 'research' ? 'researching' : 'pending',
      toolUsed: result?.tool_used,
      snippet: result?.snippet,
    }
  })

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-4 space-y-3 overflow-y-auto">
      {/* Header row with collapse toggle */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-500">
          Research Progress
          {subQuestions.length > 0 && (
            <span className="ml-1 text-slate-600">({subQuestions.length})</span>
          )}
        </p>
        <button
          onClick={() => setIsExpanded((p) => !p)}
          className="text-slate-500 hover:text-slate-300 transition-colors"
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          <svg
            className={`w-4 h-4 transition-transform duration-200 ${isExpanded ? '' : 'rotate-180'}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
          </svg>
        </button>
      </div>

      {isExpanded && (
        <>
          {/* Current node status */}
          {currentNode && NODE_LABELS[currentNode] && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="inline-block w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
              {NODE_LABELS[currentNode]}
            </div>
          )}

          {/* Sub-questions */}
          {isAwaitingInput && editableQuestions.length > 0 ? (
            <div className="space-y-3">
              <p className="text-sm font-medium text-amber-300">
                Review and edit the sub-questions below, then approve to continue:
              </p>
              {editableQuestions.map((q, i) => (
                <div key={i} className="flex gap-2 items-start">
                  <span className="text-xs text-slate-500 pt-2.5 w-5 shrink-0">{i + 1}.</span>
                  <textarea
                    value={q}
                    onChange={(e) => onEditQuestion(i, e.target.value)}
                    rows={3}
                    className="flex-1 rounded-lg border border-slate-600 bg-slate-700/60 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none leading-relaxed"
                  />
                  <button
                    onClick={() => onDeleteQuestion(i)}
                    disabled={editableQuestions.length <= 1}
                    className="mt-1 p-1.5 rounded-md text-slate-500 hover:text-red-400 hover:bg-red-900/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
                    aria-label="Delete question"
                    title="Delete question"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              ))}
              <div className="flex gap-2 pt-1">
                <button
                  onClick={onAddQuestion}
                  className="flex items-center gap-1.5 rounded-lg border border-dashed border-slate-600 px-3 py-2 text-sm text-slate-400 hover:text-slate-200 hover:border-slate-400 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add question
                </button>
                <button
                  onClick={onApproveQuestions}
                  className="flex-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition-colors"
                >
                  Approve & Continue
                </button>
              </div>
            </div>
          ) : (
            questionStates.length > 0 && (
              <div className="space-y-2">
                {questionStates.map((qs, i) => {
                  const badge = qs.toolUsed ? TOOL_BADGES[qs.toolUsed] : null
                  return (
                    <div key={i} className="rounded-lg border border-slate-700 bg-slate-900/40 p-3 space-y-1">
                      <div className="flex items-start gap-2">
                        <StatusIcon status={qs.status} />
                        <span className="text-sm text-slate-300 flex-1">{qs.question}</span>
                        {badge && (
                          <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${badge.className}`}>
                            {badge.label}
                          </span>
                        )}
                      </div>
                      {qs.snippet && (
                        <p className="text-xs text-slate-500 ml-6 line-clamp-2">{qs.snippet}</p>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          )}
        </>
      )}
    </div>
  )
}

function StatusIcon({ status }: { status: SubQuestionState['status'] }) {
  if (status === 'done') {
    return (
      <span className="text-green-400 mt-0.5 shrink-0">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      </span>
    )
  }
  if (status === 'researching') {
    return <span className="inline-block w-4 h-4 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin shrink-0 mt-0.5" />
  }
  return <span className="inline-block w-4 h-4 rounded-full border-2 border-slate-600 shrink-0 mt-0.5" />
}
