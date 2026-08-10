import { useEffect, useRef, useState } from 'react'
import { useSetSubtaskNotes } from '../hooks/useSubtasks'
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

  return (
    <div className="subtask-notepad">
      <p className="subtask-notepad-label">📝 {subtask.text}</p>
      <textarea
        className="subtask-notepad-input"
        placeholder="Notes for this subtask..."
        value={draft}
        onChange={(e) => {
          dirty.current = true
          setDraft(e.target.value)
        }}
      />
    </div>
  )
}
