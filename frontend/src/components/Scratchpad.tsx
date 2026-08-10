import { useEffect, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useScratchpad } from '../hooks/useScratchpad'
import { useFormattableTextarea } from '../context/FormattingContext'
import { isTypingElement } from '../utils/isTypingElement'
import { ExpandOverlay } from './ExpandOverlay'

export function Scratchpad() {
  const { user } = useAuth()
  const [text, setText] = useScratchpad(user?.username)
  const [expanded, setExpanded] = useState(false)
  const compact = useFormattableTextarea(setText)
  const expandedField = useFormattableTextarea(setText)

  // Bubble-phase, so a SubtaskNotepad's capture-phase listener (see its own
  // comment) gets first refusal on `` ` `` while a notepad is open.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== '`') return
      if (isTypingElement(document.activeElement)) return
      e.preventDefault()
      compact.ref.current?.focus()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [compact.ref])

  return (
    <div className="scratchpad" data-focus-exempt>
      <div className="panel-header-row">
        <p className="scratchpad-label">Scratchpad</p>
        <button type="button" className="expand-btn" title="Expand" onClick={() => setExpanded(true)}>
          ⤢
        </button>
      </div>
      <textarea
        ref={compact.ref}
        className="scratchpad-input"
        placeholder="Press ` to focus..."
        value={text}
        onChange={(e) => setText(e.target.value)}
        onFocus={compact.onFocus}
        onBlur={compact.onBlur}
        onKeyDown={compact.onKeyDown}
      />
      <AnimatePresence>
        {expanded && (
          <ExpandOverlay label="Scratchpad" onClose={() => setExpanded(false)}>
            <textarea
              ref={expandedField.ref}
              className="expand-overlay-input"
              placeholder="Press ` to focus..."
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              onFocus={expandedField.onFocus}
              onBlur={expandedField.onBlur}
              onKeyDown={expandedField.onKeyDown}
            />
          </ExpandOverlay>
        )}
      </AnimatePresence>
    </div>
  )
}
