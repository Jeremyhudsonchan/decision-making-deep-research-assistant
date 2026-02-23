'use client'

import { useState, KeyboardEvent } from 'react'

interface ChatInputProps {
  onSubmit: (query: string) => void
  disabled?: boolean
  placeholder?: string
}

export default function ChatInput({ onSubmit, disabled, placeholder }: ChatInputProps) {
  const [value, setValue] = useState('')

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex gap-3 items-end">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder || 'Ask a research question... (Enter to submit, Shift+Enter for newline)'}
        rows={3}
        className={`
          flex-1 resize-none rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-3
          text-slate-200 placeholder-slate-500 text-sm
          focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent
          transition-colors
          ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
        `}
      />
      <button
        onClick={handleSubmit}
        disabled={disabled || !value.trim()}
        className={`
          rounded-xl px-5 py-3 font-semibold text-sm transition-all
          bg-indigo-600 hover:bg-indigo-500 text-white
          disabled:opacity-40 disabled:cursor-not-allowed
          focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-[#0f1117]
        `}
      >
        Research
      </button>
    </div>
  )
}
