import { useEffect, useRef, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useSetSubtaskNotes } from '../hooks/useSubtasks'
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
  const ref = useRef<HTMLTextAreaElement>(null)
  const [expanded, setExpanded] = useState(false)

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
      ref.current?.focus()
    }
    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [])

  const onChange = (value: string) => {
    dirty.current = true
    setDraft(value)
  }

  return (
    <div className="subtask-notepad" data-focus-exempt>
      <div className="panel-header-row">
        <p className="subtask-notepad-label">📝 {subtask.text}</p>
        <button type="button" className="expand-btn" title="Expand" onClick={() => setExpanded(true)}>
          ⤢
        </button>
      </div>
      <textarea
        ref={ref}
        className="subtask-notepad-input"
        placeholder="Notes for this subtask... (Press ` to focus)"
        value={draft}
        onChange={(e) => onChange(e.target.value)}
      />
      <AnimatePresence>
        {expanded && (
          <ExpandOverlay label={subtask.text} onClose={() => setExpanded(false)} accent>
            <textarea
              className="expand-overlay-input"
              placeholder="Notes for this subtask..."
              autoFocus
              value={draft}
              onChange={(e) => onChange(e.target.value)}
            />
          </ExpandOverlay>
        )}
      </AnimatePresence>
    </div>
  )
}
