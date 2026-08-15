import { useEffect, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useScratchpad } from '../hooks/useScratchpad'
import { useFormattableEditable } from '../context/FormattingContext'
import { useSyncEditableContent } from '../hooks/useSyncEditableContent'
import { isTypingElement } from '../utils/isTypingElement'
import { ExpandOverlay } from './ExpandOverlay'

export function Scratchpad() {
  const { user } = useAuth()
  const [text, setText] = useScratchpad(user?.username)
  const [expanded, setExpanded] = useState(false)
  const compact = useFormattableEditable(setText)
  const expandedField = useFormattableEditable(setText)

  useSyncEditableContent(compact.ref, text, () => document.activeElement === compact.ref.current)

  // The expanded overlay only exists in the DOM while open, and nothing else
  // can change `text` while it's up (the compact copy behind the blur isn't
  // reachable) - so it only ever needs its content set once, right as it
  // mounts, not kept continuously synced the way the compact copy is.
  useEffect(() => {
    if (!expanded) return
    const el = expandedField.ref.current
    if (!el) return
    el.innerHTML = text
    el.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded])

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
      <div
        ref={compact.ref}
        className="scratchpad-input rich-text-input"
        contentEditable
        suppressContentEditableWarning
        data-placeholder="Press ` to focus..."
        onInput={compact.onInput}
        onFocus={compact.onFocus}
        onBlur={compact.onBlur}
        onKeyDown={compact.onKeyDown}
      />
      <AnimatePresence>
        {expanded && (
          <ExpandOverlay label="Scratchpad" onClose={() => setExpanded(false)}>
            <div
              ref={expandedField.ref}
              className="expand-overlay-input rich-text-input"
              contentEditable
              suppressContentEditableWarning
              data-placeholder="Press ` to focus..."
              onInput={expandedField.onInput}
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
