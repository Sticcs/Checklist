import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import type { Task } from '../types'
import { useSetTaskNotes } from '../hooks/useTasks'
import { useFormattableEditable } from '../context/FormattingContext'
import { useSyncEditableContent } from '../hooks/useSyncEditableContent'

interface Props {
  task: Task
  onBack: () => void
}

// A due date is a plain yyyy-mm-dd (no time of day) - the countdown treats
// the assignment as due at the end of that day (23:59:59 local), matching
// how "due today"/"overdue" are already judged everywhere else in the app
// (see daysUntil in dueDatePresets.ts), rather than inventing a separate,
// stricter midnight-start cutoff just for this timer.
function deadlineFor(dueDate: string): Date {
  return new Date(`${dueDate}T23:59:59`)
}

function formatRemaining(ms: number): string {
  const overdue = ms < 0
  const abs = Math.abs(ms)
  const totalSeconds = Math.floor(abs / 1000)
  const days = Math.floor(totalSeconds / 86_400)
  const hours = Math.floor((totalSeconds % 86_400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const parts: string[] = []
  if (days > 0) parts.push(`${days}d`)
  parts.push(`${hours}h`, `${minutes}m`, `${seconds}s`)
  return overdue ? `Overdue by ${parts.join(' ')}` : `${parts.join(' ')} remaining`
}

// Full-page focused writing space for a single assessment - deliberately
// shows nothing else from the main app (no task list, entry form, sidebar,
// or scratchpad), the same way AuthPage replaces TaskListPage wholesale (see
// App.tsx). Mounted/unmounted by TaskListPage, which also owns the
// AnimatePresence + slide transition around it.
export function AssignmentWorkspace({ task, onBack }: Props) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const handle = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(handle)
  }, [])

  const [draft, setDraft] = useState(task.notes ?? '')
  const dirty = useRef(false)
  const setTaskNotes = useSetTaskNotes()

  const onChange = (value: string) => {
    dirty.current = true
    setDraft(value)
  }

  const notesField = useFormattableEditable(onChange)
  useSyncEditableContent(notesField.ref, draft, () => dirty.current)

  useEffect(() => {
    if (!dirty.current) setDraft(task.notes ?? '')
  }, [task.notes])

  useEffect(() => {
    if (!dirty.current) return
    const handle = setTimeout(() => {
      dirty.current = false
      setTaskNotes.mutate({ id: task.id, notes: draft })
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, 600)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  const remainingMs = task.due_date ? deadlineFor(task.due_date).getTime() - now.getTime() : null

  return (
    <motion.div
      className="assignment-workspace"
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 40 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
    >
      <button type="button" className="assignment-workspace-back-btn" title="Back" onClick={onBack}>
        ←
      </button>
      <div className="assignment-workspace-header">
        <h1 className="assignment-workspace-title">{task.text}</h1>
        {remainingMs !== null ? (
          <p className={remainingMs < 0 ? 'assignment-countdown overdue' : 'assignment-countdown'}>
            {formatRemaining(remainingMs)}
          </p>
        ) : (
          <p className="assignment-countdown no-due-date">No due date set</p>
        )}
      </div>
      <div
        ref={notesField.ref}
        className="assignment-workspace-textbox rich-text-input"
        contentEditable
        suppressContentEditableWarning
        data-placeholder="Start writing..."
        onInput={notesField.onInput}
        onFocus={notesField.onFocus}
        onBlur={notesField.onBlur}
        onKeyDown={notesField.onKeyDown}
      />
    </motion.div>
  )
}
