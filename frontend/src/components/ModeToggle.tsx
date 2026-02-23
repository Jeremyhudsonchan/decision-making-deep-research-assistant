'use client'

interface ModeToggleProps {
  interactive: boolean
  onChange: (interactive: boolean) => void
  disabled?: boolean
}

export default function ModeToggle({ interactive, onChange, disabled }: ModeToggleProps) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={!interactive ? 'text-indigo-400 font-semibold' : 'text-slate-500'}>
        Autonomous
      </span>
      <button
        onClick={() => !disabled && onChange(!interactive)}
        disabled={disabled}
        className={`
          relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent
          transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-[#0f1117]
          ${interactive ? 'bg-indigo-600' : 'bg-slate-700'}
          ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
        `}
        role="switch"
        aria-checked={interactive}
        title={interactive ? 'Interactive mode: agent pauses for your input' : 'Autonomous mode: agent runs fully automatically'}
      >
        <span
          className={`
            pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0
            transition duration-200 ease-in-out
            ${interactive ? 'translate-x-5' : 'translate-x-0'}
          `}
        />
      </button>
      <span className={interactive ? 'text-indigo-400 font-semibold' : 'text-slate-500'}>
        Interactive
      </span>
      {interactive && (
        <span className="text-xs text-slate-400 ml-1">(agent pauses for your input)</span>
      )}
    </div>
  )
}
