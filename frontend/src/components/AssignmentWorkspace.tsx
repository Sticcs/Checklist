import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import type { Task } from '../types'
import { useSetTaskNotes } from '../hooks/useTasks'
import { useFormattableEditable, useFormattingContext, type FormatKind } from '../context/FormattingContext'
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

// Persisted across sessions (same convention as theme/settings, see
// SettingsContext) rather than reset every time the workspace opens - a
// comfortable reading/writing size, once set, is a standing preference, not
// a per-assignment one.
const FONT_SIZE_KEY = 'checklist-assignment-font-size'
const MIN_FONT_REM = 0.8
const MAX_FONT_REM = 2.4
const FONT_STEP_REM = 0.1
const DEFAULT_FONT_REM = 1.05

function loadFontSize(): number {
  const raw = localStorage.getItem(FONT_SIZE_KEY)
  const parsed = raw ? Number.parseFloat(raw) : NaN
  return Number.isFinite(parsed) ? Math.min(MAX_FONT_REM, Math.max(MIN_FONT_REM, parsed)) : DEFAULT_FONT_REM
}

const FORMAT_BUTTONS: Array<{ kind: FormatKind; title: string; glyph: React.ReactNode }> = [
  { kind: 'bold', title: 'Bold (Ctrl/Cmd+B)', glyph: <b>B</b> },
  { kind: 'italic', title: 'Italic (Ctrl/Cmd+I)', glyph: <i>I</i> },
  { kind: 'underline', title: 'Underline (Ctrl/Cmd+U)', glyph: <u>U</u> },
]

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
  const [fontSize, setFontSize] = useState(loadFontSize)

  useEffect(() => {
    localStorage.setItem(FONT_SIZE_KEY, String(fontSize))
  }, [fontSize])

  const onChange = (value: string) => {
    dirty.current = true
    setDraft(value)
  }

  const notesField = useFormattableEditable(onChange)
  useSyncEditableContent(notesField.ref, draft, () => dirty.current)
  // Bold/Italic/Underline buttons below act on whichever editor is
  // currently registered as focused (see FormattingContext) - the same
  // mechanism the sidebar's own B/I/U buttons use for the scratchpad/notes
  // fields, needed here too since this page has no sidebar to borrow them
  // from, and touch devices (iPad) have no Ctrl/Cmd+B-style shortcut.
  const { active: formattingActive, applyFormat } = useFormattingContext()

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
      // The task-list page's document-level click handler (see
      // TaskListPage) treats any click outside a task card as "clear
      // focus" - without this, clicking anywhere in here (the textbox, the
      // toolbar, the back zone) would clear the assessment's focused/
      // selected state in the background, so it'd no longer show as
      // selected (and its Start button/badges would vanish) the moment you
      // go back.
      data-focus-exempt
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 40 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
    >
      {/* A large tap/click zone (not just the small arrow glyph) running the
          full height of the left edge - the glyph alone was easy to miss
          and hard to hit precisely on a touch screen. */}
      <button type="button" className="assignment-workspace-back-zone" title="Back" onClick={onBack}>
        <span className="assignment-workspace-back-icon">←</span>
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

      <div className="assignment-toolbar" data-focus-exempt>
        <div className="assignment-toolbar-group">
          {FORMAT_BUTTONS.map(({ kind, title, glyph }) => (
            <button
              key={kind}
              type="button"
              className={formattingActive ? 'icon-btn btn-primary' : 'icon-btn'}
              disabled={!formattingActive}
              title={title}
              // Keeps focus (and the selection) inside the textbox instead
              // of moving it to this button, which is what a plain click
              // would do - applyFormat needs that selection intact.
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => applyFormat(kind)}
            >
              {glyph}
            </button>
          ))}
        </div>
        <div className="assignment-toolbar-group">
          <button
            type="button"
            className="icon-btn"
            title="Decrease font size"
            disabled={fontSize <= MIN_FONT_REM}
            onClick={() => setFontSize((f) => Math.max(MIN_FONT_REM, +(f - FONT_STEP_REM).toFixed(2)))}
          >
            A−
          </button>
          <button
            type="button"
            className="icon-btn"
            title="Increase font size"
            disabled={fontSize >= MAX_FONT_REM}
            onClick={() => setFontSize((f) => Math.min(MAX_FONT_REM, +(f + FONT_STEP_REM).toFixed(2)))}
          >
            A+
          </button>
        </div>
      </div>

      <div
        ref={notesField.ref}
        className="assignment-workspace-textbox rich-text-input"
        style={{ fontSize: `${fontSize}rem` }}
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
