import { useEffect, useRef, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useSetSubtaskNotes } from '../hooks/useSubtasks'
import { useFormattableEditable } from '../context/FormattingContext'
import { useSyncEditableContent } from '../hooks/useSyncEditableContent'
import { isTypingElement } from '../utils/isTypingElement'
import { ExpandOverlay } from './ExpandOverlay'
import type { Subtask } from '../types'

interface Props {
  subtask: Subtask
}

// Mounted fresh (via a `key={subtask.id}` at the call site) whenever focus
// switches to a different subtask, so the draft always starts from that
// subtask's own notes instead of carrying over the previous one's.
export function SubtaskNotepad({ subtask }: Props) {
  const [draft, setDraft] = useState(subtask.notes ?? '')
  const dirty = useRef(false)
  const setSubtaskNotes = useSetSubtaskNotes()
  const [expanded, setExpanded] = useState(false)

  const onChange = (value: string) => {
    dirty.current = true
    setDraft(value)
  }

  const compact = useFormattableEditable(onChange)
  const expandedField = useFormattableEditable(onChange)

  useSyncEditableContent(compact.ref, draft, () => dirty.current)

  // Only overwrite the draft from server state when we're not the source of
  // the change - see the matching comment on TaskCard's notes handling.
  useEffect(() => {
    if (!dirty.current) setDraft(subtask.notes ?? '')
  }, [subtask.notes])

  useEffect(() => {
    if (!dirty.current) return
    const handle = setTimeout(() => {
      dirty.current = false
      setSubtaskNotes.mutate({ subtaskId: subtask.id, notes: draft })
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, 600)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  // Takes `` ` `` away from the scratchpad while a subtask notepad is open -
  // registered in the capture phase, which document always runs before its
  // own bubble-phase listeners (Scratchpad's) regardless of mount order, and
  // stopPropagation keeps Scratchpad's handler from then stealing focus back
  // in the same keystroke.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== '`') return
      if (isTypingElement(document.activeElement)) return
      e.preventDefault()
      e.stopPropagation()
      compact.ref.current?.focus()
    }
    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [compact.ref])

  // The expanded overlay only exists in the DOM while open, and nothing else
  // can change `draft` while it's up (the compact copy behind the blur
  // isn't reachable) - so it only ever needs its content set once, right as
  // it mounts. autoFocus doesn't apply to a plain <div> the way it does a
  // <textarea>, so this also replaces that.
  useEffect(() => {
    if (!expanded) return
    const el = expandedField.ref.current
    if (!el) return
    el.innerHTML = draft
    el.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded])

  return (
    <div className="subtask-notepad" data-focus-exempt>
      <div className="panel-header-row">
        <p className="subtask-notepad-label">📝 {subtask.text}</p>
        <button type="button" className="expand-btn" title="Expand" onClick={() => setExpanded(true)}>
          ⤢
        </button>
      </div>
      <div
        ref={compact.ref}
        className="subtask-notepad-input rich-text-input"
        contentEditable
        suppressContentEditableWarning
        data-placeholder="Notes for this subtask... (Press ` to focus)"
        onInput={compact.onInput}
        onFocus={compact.onFocus}
        onBlur={compact.onBlur}
        onKeyDown={compact.onKeyDown}
      />
      <AnimatePresence>
        {expanded && (
          <ExpandOverlay label={subtask.text} onClose={() => setExpanded(false)} accent>
            <div
              ref={expandedField.ref}
              className="expand-overlay-input rich-text-input"
              contentEditable
              suppressContentEditableWarning
              data-placeholder="Notes for this subtask..."
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
