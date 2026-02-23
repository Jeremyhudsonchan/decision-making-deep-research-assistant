'use client'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface MessageListProps {
  messages: Message[]
}

export default function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
        <div className="text-center space-y-2">
          <div className="text-4xl">🔬</div>
          <p className="font-medium text-slate-400">Deep Research Assistant</p>
          <p>Ask a complex research question to get started.</p>
          <p className="text-xs">Powered by LangGraph + Tavily + Yahoo Finance</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto space-y-4 pr-1">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div
            className={`
              max-w-[85%] rounded-2xl px-4 py-3 text-sm
              ${msg.role === 'user'
                ? 'bg-indigo-600 text-white rounded-br-sm'
                : 'bg-slate-800 border border-slate-700 text-slate-200 rounded-bl-sm'
              }
            `}
          >
            {msg.role === 'assistant' ? (
              <div
                className="prose-answer whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: formatAnswer(msg.content) }}
              />
            ) : (
              <p className="whitespace-pre-wrap">{msg.content}</p>
            )}
            <p className={`text-xs mt-1 ${msg.role === 'user' ? 'text-indigo-300' : 'text-slate-500'}`}>
              {msg.timestamp.toLocaleTimeString()}
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Very lightweight markdown-like formatting for answers.
 * Converts **bold**, `code`, and line breaks.
 */
function formatAnswer(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}
