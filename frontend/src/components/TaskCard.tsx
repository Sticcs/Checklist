import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, Reorder, useDragControls } from 'framer-motion'
import { toast } from 'sonner'
import type { Task } from '../types'
import { CATEGORIES, PRIORITIES } from '../constants'
import { useSettings } from '../context/SettingsContext'
import { useFormattableEditable } from '../context/FormattingContext'
import { useSyncEditableContent } from '../hooks/useSyncEditableContent'
import {
  useDeleteTask,
  useEditTask,
  useSetPinned,
  useSetTaskNotes,
  useToggleDone,
} from '../hooks/useTasks'
import {
  useAddSubtask,
  useDeleteSubtask,
  useSetSubtaskDueDate,
  useSetSubtaskUrgent,
  useToggleSubtask,
} from '../hooks/useSubtasks'
import { daysUntil } from '../utils/dueDatePresets'
import { copyTextToClipboard, formatAsOutline } from '../utils/copyAsText'
import { DateInput } from './DateInput'
import { useDraftText, readPendingDraft, writePendingDraft, clearPendingDraft } from '../hooks/useDraftText'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { ApiError } from '../api/client'

interface Props {
  task: Task
  focused: boolean
  todayIso: string
  onExpandSubtasks?: (taskId: number) => void
  draggable?: boolean
  onDragEnd?: (taskId: number) => void
  focusedSubtaskId?: number | null
  notepadHidden?: boolean
  onToggleNotepad?: () => void
  assignedCount?: number
  onShowAssignments?: (taskId: number) => void
  compact?: boolean
  highlighted?: boolean
}

export function TaskCard({
  task,
  focused,
  todayIso,
  onExpandSubtasks,
  draggable,
  onDragEnd,
  focusedSubtaskId = null,
  notepadHidden = false,
  onToggleNotepad,
  assignedCount = 0,
  onShowAssignments,
  compact = false,
  highlighted = false,
}: Props) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(task.text)
  const [editPriority, setEditPriority] = useState(task.priority)
  const [editCategory, setEditCategory] = useState(task.category)
  const [editDueDate, setEditDueDate] = useState(task.due_date ?? '')

  const [subtasksOpen, setSubtasksOpen] = useState(false)
  const [newSubtaskText, setNewSubtaskText] = useDraftText(`subtask-add:${task.id}`)

  const notesDraftKey = `task-notes:${task.id}`
  const [notesOpen, setNotesOpen] = useState(false)
  // A pending localStorage draft (an edit that never made it to the server -
  // see the debounce effect below) wins over the server's own notes so a
  // reload doesn't silently drop it in favor of the stale server copy.
  const [notesDraft, setNotesDraft] = useState(() => readPendingDraft<string>(notesDraftKey) ?? task.notes ?? '')
  const notesDirty = useRef(readPendingDraft<string>(notesDraftKey) !== null)
  const online = useOnlineStatus()

  const [dueDatePickerSubtaskId, setDueDatePickerSubtaskId] = useState<number | null>(null)
  // Drives the compact-view subtask dropdown's animated reveal (see the
  // AnimatePresence around .compact-subtask-list below) - a plain CSS
  // :hover toggle can't animate an instant display:none/flex swap, so this
  // tracks hover as real state instead.
  const [hovered, setHovered] = useState(false)
  const [compactMenuOpen, setCompactMenuOpen] = useState(false)
  const compactMenuRef = useRef<HTMLDivElement>(null)

  // Closes the compact-row's "⋮" menu on any click outside it - same pattern
  // as the assignment workspace's color popover.
  useEffect(() => {
    if (!compactMenuOpen) return
    const handler = (e: MouseEvent) => {
      if (!compactMenuRef.current?.contains(e.target as Node)) setCompactMenuOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [compactMenuOpen])

  const { urgentWindowDays } = useSettings()

  const setPinned = useSetPinned()
  const toggleDone = useToggleDone()
  const editTask = useEditTask()
  const deleteTask = useDeleteTask()
  const addSubtask = useAddSubtask()
  const toggleSubtask = useToggleSubtask()
  const setSubtaskUrgent = useSetSubtaskUrgent()
  const setSubtaskDueDate = useSetSubtaskDueDate()
  const deleteSubtask = useDeleteSubtask()
  const setTaskNotes = useSetTaskNotes()
  const dragControls = useDragControls()

  const overdue = !!task.due_date && !task.done && task.due_date < todayIso
  const daysToDue = task.due_date ? daysUntil(task.due_date, todayIso) : null
  const dueUrgent = !task.done && daysToDue !== null && daysToDue >= 0 && daysToDue <= urgentWindowDays
  const dueSoon = !dueUrgent && !task.done && daysToDue !== null && daysToDue > 0 && daysToDue <= 3
  const subDone = task.subtasks.filter((s) => s.done).length
  const urgentSubtaskCount = task.subtasks.filter((s) => s.urgent).length

  // The one due-date indicator that stays visible on the quiet, unhovered
  // card - folds what used to be three separate badges (the raw date, a
  // "🚨 Urgent!" badge, and a "⏳ Due in N days" badge) into a single piece
  // of text, styled by how pressing it is, instead of three things
  // competing for the same glance.
  const dueDateClass = overdue || dueUrgent ? 'task-due-inline overdue' : dueSoon ? 'task-due-inline warm' : 'task-due-inline'
  const dueDateLabel = overdue
    ? `${Math.abs(daysToDue ?? 0)} day${Math.abs(daysToDue ?? 0) === 1 ? '' : 's'} overdue`
    : dueUrgent || dueSoon
      ? daysToDue === 0
        ? 'due today'
        : `due in ${daysToDue} day${daysToDue === 1 ? '' : 's'}`
      : task.due_date

  // Everything besides checkbox/pin/title/due-date lives in a reveal row
  // that's hidden until you hover or focus the card (see .task-reveal) - but
  // once notes or subtasks are actually open, keep it visible even after the
  // mouse leaves, so the button that closes them (and the rest of the row)
  // doesn't vanish out from under you mid-edit.
  const revealOpen = focused || notesOpen || subtasksOpen

  // Tally not-done subtasks by days-until-due, so "3 subtasks due in 2 days"
  // and "1 subtask due in 5 days" show as separate counts instead of being
  // flattened into one combined number.
  const subtaskDueTally = (() => {
    const counts = new Map<number, number>()
    for (const s of task.subtasks) {
      if (s.done || !s.due_date) continue
      const d = daysUntil(s.due_date, todayIso)
      counts.set(d, (counts.get(d) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => a[0] - b[0])
  })()
  // Includes the leading count itself (not just appended by the caller) so
  // the comma can be placed exactly where two numbers actually collide -
  // "1 13 days overdue" needs it ("1, 13 days overdue"), but "1 due today"
  // and "1 due in 3 days" never had two adjacent numbers to begin with, and
  // a comma before "due" there just reads oddly.
  const subtaskDueTallyText = (count: number, d: number): string =>
    d < 0
      ? `${count}, ${Math.abs(d)} day${Math.abs(d) === 1 ? '' : 's'} overdue`
      : d === 0
        ? `${count} due today`
        : `${count} due in ${d} day${d === 1 ? '' : 's'}`

  // The tally row's fade-to-transparent mask should only show up when a
  // badge is actually being clipped at the right edge - measured directly
  // rather than assumed, so it doesn't fade out the last badge on a row
  // that has plenty of room to spare.
  const tallyRowRef = useRef<HTMLDivElement>(null)
  const [tallyOverflowing, setTallyOverflowing] = useState(false)
  useEffect(() => {
    const el = tallyRowRef.current
    if (!el) {
      setTallyOverflowing(false)
      return
    }
    const check = () => setTallyOverflowing(el.scrollWidth > el.clientWidth + 1)
    check()
    const observer = new ResizeObserver(check)
    observer.observe(el)
    return () => observer.disconnect()
    // subtaskDueTally is a fresh array every render - key off its actual
    // contents instead, so this doesn't tear down/rebuild the observer on
    // every unrelated re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subtaskDueTally.map(([d, c]) => `${d}:${c}`).join(',')])

  // A one-shot glow that plays exactly once on the false->true transition
  // (not on every render while done, and not on initial mount if the task
  // was already done when it loaded).
  const [justCompleted, setJustCompleted] = useState(false)
  const wasDone = useRef(task.done)
  useEffect(() => {
    const previouslyDone = wasDone.current
    wasDone.current = task.done
    if (!previouslyDone && task.done) {
      setJustCompleted(true)
      const handle = setTimeout(() => setJustCompleted(false), 1000)
      return () => clearTimeout(handle)
    }
  }, [task.done])

  // Only overwrite the draft from server state when we're not the source of
  // the change (i.e. no unsaved local edit in flight) - otherwise the
  // debounced save landing mid-typing would fight the user's own keystrokes.
  useEffect(() => {
    if (!notesDirty.current) setNotesDraft(task.notes ?? '')
  }, [task.notes])

  const saveNotes = () => {
    notesDirty.current = false
    setTaskNotes.mutate(
      { id: task.id, notes: notesDraft },
      {
        onSuccess: () => clearPendingDraft(notesDraftKey),
        onError: (err) => {
          // A network failure, not a real rejection - the draft is still
          // safe in localStorage (written on every keystroke below), and
          // staying dirty means the next edit or the next reconnect (see
          // the online-triggered effect below) tries again.
          if (!(err instanceof ApiError)) notesDirty.current = true
        },
      }
    )
  }

  useEffect(() => {
    if (!notesDirty.current) return
    const handle = setTimeout(saveNotes, 600)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notesDraft])

  useEffect(() => {
    if (online && notesDirty.current) saveNotes()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online])

  // Clicking to focus a task is also how you get at its subtasks now - open
  // the panel the moment focus lands, close it the moment focus leaves,
  // without needing a separate click on the toggle button first.
  useEffect(() => {
    setSubtasksOpen(focused)
  }, [focused])

  const toggleSubtasksOpen = () => {
    const next = !subtasksOpen
    setSubtasksOpen(next)
    if (next) onExpandSubtasks?.(task.id)
  }

  const handleNotesChange = (value: string) => {
    notesDirty.current = true
    writePendingDraft(notesDraftKey, value)
    setNotesDraft(value)
  }

  const notesField = useFormattableEditable(handleNotesChange)
  useSyncEditableContent(notesField.ref, notesDraft, () => notesDirty.current)

  // The notes box only exists in the DOM while notesOpen is true (see
  // below), unlike most of this card - useSyncEditableContent's effect is
  // keyed on notesDraft's value, so if that value hasn't changed since
  // before the box existed (the common case: notes already loaded, panel
  // just opened for the first time this session), the box would otherwise
  // mount and stay empty even though notesDraft is correct. Same fix
  // SubtaskNotepad's expanded overlay already uses for the same reason.
  useEffect(() => {
    if (!notesOpen || notesDirty.current) return
    const el = notesField.ref.current
    if (el) el.innerHTML = notesDraft
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notesOpen])

  const startEditing = () => {
    setEditText(task.text)
    setEditPriority(task.priority)
    setEditCategory(task.category)
    setEditDueDate(task.due_date ?? '')
    setEditing(true)
  }

  const handleCopyAsText = async () => {
    const text = formatAsOutline(
      task.text,
      task.subtasks.map((s) => s.text)
    )
    const ok = await copyTextToClipboard(text)
    if (ok) toast.success('Copied to clipboard')
    else toast.error('Could not copy to clipboard')
  }

  const saveEdit = (e: React.FormEvent) => {
    e.preventDefault()
    // Close immediately - the mutation is optimistic, so there's no need to
    // wait on the round trip before showing the edited task.
    setEditing(false)
    editTask.mutate({
      id: task.id,
      text: editText.trim(),
      priority: editPriority,
      category: editCategory,
      dueDate: editDueDate || null,
    })
  }

  const submitSubtask = (e: React.FormEvent) => {
    e.preventDefault()
    const text = newSubtaskText.trim()
    if (!text) return
    setNewSubtaskText('')
    addSubtask.mutate({ taskId: task.id, text })
  }

  // Pasting a multi-line list (bullet points, a numbered list, or just one
  // item per line) adds each line as its own subtask instead of dumping the
  // whole block into the input as one line. A single-line paste is left
  // alone - the browser's normal paste-into-input behavior handles that.
  const handleSubtaskPaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    const pasted = e.clipboardData.getData('text')
    const lines = pasted
      .split(/\r?\n/)
      .map((line) => line.trim().replace(/^(?:[-*•‣▪·]|\(?\d+[.)])\s+/, '').trim())
      .filter(Boolean)
    if (lines.length < 2) return
    e.preventDefault()
    setNewSubtaskText('')
    for (const line of lines) {
      addSubtask.mutate({ taskId: task.id, text: line })
    }
  }

  const content = (
    <>
      {editing ? (
        <form className="edit-form" onSubmit={saveEdit}>
          <input value={editText} onChange={(e) => setEditText(e.target.value)} />
          <div className="edit-form-row">
            <select value={editPriority} onChange={(e) => setEditPriority(e.target.value)}>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <select value={editCategory} onChange={(e) => setEditCategory(e.target.value)}>
              {CATEGORIES.filter((c) => c !== 'Custom').map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <DateInput value={editDueDate} onCommit={setEditDueDate} />
          </div>
          <div className="edit-form-actions">
            <button type="submit" className="btn-primary">
              Save
            </button>
            <button type="button" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : compact ? (
        <div data-task-content-id={task.id} className="compact-row">
          <input
            type="checkbox"
            className="task-done-checkbox"
            checked={task.done}
            title="Mark complete"
            onChange={() => toggleDone.mutate({ id: task.id, done: !task.done })}
          />
          <span className={task.done ? 'compact-row-title done' : 'compact-row-title'}>{task.text}</span>
          <span className="compact-row-due">{task.due_date ?? ''}</span>
          <button
            type="button"
            className={task.pinned ? 'compact-star-btn pinned' : 'compact-star-btn'}
            aria-pressed={task.pinned}
            title={task.pinned ? 'Unpin' : 'Pin (mark important)'}
            onClick={() => setPinned.mutate({ id: task.id, pinned: !task.pinned })}
          >
            {task.pinned ? '★' : '☆'}
          </button>
          <div className="compact-row-actions" ref={compactMenuRef}>
            <button
              type="button"
              className="compact-menu-btn"
              aria-expanded={compactMenuOpen}
              title="More actions"
              onClick={() => setCompactMenuOpen((open) => !open)}
            >
              ⋮
            </button>
            {compactMenuOpen && (
              <div className="compact-menu-popover" data-focus-exempt>
                <button
                  type="button"
                  onClick={() => {
                    setCompactMenuOpen(false)
                    void handleCopyAsText()
                  }}
                >
                  📄 Copy as text
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCompactMenuOpen(false)
                    startEditing()
                  }}
                >
                  ✏️ Edit
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCompactMenuOpen(false)
                    deleteTask.mutate(task.id)
                  }}
                >
                  🗑️ Delete
                </button>
              </div>
            )}
          </div>
        </div>
      ) : (
        // Quiet by default: checkbox, an optional pin glyph, the title, and
        // a due-date indicator (styled by urgency) are the only things on
        // screen until you hover or focus the card. Category, assigned
        // count, urgent/due-tally badges, notes, subtasks, and the pin/edit/
        // delete actions all still exist - they live in .task-reveal below,
        // which only expands on hover/focus (see the matching CSS) or while
        // notes/subtasks are actually open (see revealOpen above). Nothing
        // here is a new feature; it's the same controls as before, just not
        // all shouting on the card at once.
        <div data-task-content-id={task.id} className="task-content">
          {draggable && (
            <span
              className="drag-handle"
              title="Drag to reorder"
              onPointerDown={(e) => dragControls.start(e)}
            >
              ⠿
            </span>
          )}
          <input
            type="checkbox"
            className="task-done-checkbox"
            checked={task.done}
            title="Mark complete"
            onChange={() => toggleDone.mutate({ id: task.id, done: !task.done })}
          />
          {task.pinned && (
            <span className="pin-badge" title="Pinned">
              📌
            </span>
          )}
          <span className={task.done ? 'task-text done' : 'task-text'} title={task.text}>
            {task.text}
          </span>
          {task.due_date && <span className={dueDateClass}>{dueDateLabel}</span>}

          <div className={revealOpen ? 'task-reveal force-open' : 'task-reveal'} data-focus-exempt>
            <span className="badge">{task.category}</span>
            {assignedCount > 0 && (
              <button
                type="button"
                className="badge assigned-count-badge"
                title="Show the assessments assigned under this task"
                onClick={(e) => {
                  // Otherwise bubbles up to the document-level click
                  // delegation (see TaskListPage) and also toggles this
                  // task's focus - this button's click should only ever
                  // trigger the highlight, nothing else.
                  e.stopPropagation()
                  onShowAssignments?.(task.id)
                }}
              >
                🔗 {assignedCount}
              </button>
            )}
            {urgentSubtaskCount > 0 && (
              <span className="urgent-subtask-badge" title={`${urgentSubtaskCount} urgent subtask(s)`}>
                🔥 {urgentSubtaskCount}
              </span>
            )}
            {subtaskDueTally.length > 0 && (
              <div
                ref={tallyRowRef}
                className={tallyOverflowing ? 'subtask-due-tally-row overflowing' : 'subtask-due-tally-row'}
              >
                {subtaskDueTally.map(([d, count]) => (
                  <span key={d} className="subtask-due-tally-badge" title="Subtask due dates">
                    📅 {subtaskDueTallyText(count, d)}
                  </span>
                ))}
              </div>
            )}
            <button
              type="button"
              className="badge subtask-toggle-pill"
              title="Toggle subtasks"
              onClick={(e) => {
                e.stopPropagation()
                toggleSubtasksOpen()
              }}
            >
              {task.subtasks.length > 0 ? `📋 ${subDone}/${task.subtasks.length}` : '📋 Add subtasks'}
            </button>
            <button
              type="button"
              className={task.notes ? 'icon-btn btn-primary' : 'icon-btn'}
              title={task.notes ? 'Notes' : 'Add notes'}
              onClick={(e) => {
                e.stopPropagation()
                setNotesOpen((prev) => !prev)
              }}
            >
              📝
            </button>
            <button
              type="button"
              className={task.pinned ? 'icon-btn btn-primary' : 'icon-btn'}
              aria-pressed={task.pinned}
              title={task.pinned ? 'Unpin' : 'Pin (mark important)'}
              onClick={(e) => {
                e.stopPropagation()
                setPinned.mutate({ id: task.id, pinned: !task.pinned })
              }}
            >
              📌
            </button>
            <button
              type="button"
              className="icon-btn"
              title="Copy as text"
              onClick={(e) => {
                e.stopPropagation()
                void handleCopyAsText()
              }}
            >
              📄
            </button>
            <button
              type="button"
              className="icon-btn"
              title="Edit"
              onClick={(e) => {
                e.stopPropagation()
                startEditing()
              }}
            >
              ✏️
            </button>
            <button
              type="button"
              className="icon-btn"
              title="Delete"
              onClick={(e) => {
                e.stopPropagation()
                deleteTask.mutate(task.id)
              }}
            >
              🗑️
            </button>
          </div>
        </div>
      )}

      {/* Streamlined stand-in for the full subtask panel above - just a
          checkbox, text, and due date per row, matching the compact row
          it sits under (see the compact-view Sidebar toggle). Not shown
          while editing (the edit form only covers the task's own text/
          priority/category/date; switch back to the full view for deeper
          subtask management). Mounts/unmounts on hover (see `hovered`)
          rather than a plain CSS display toggle, so AnimatePresence can
          actually animate the reveal instead of snapping it open/closed. */}
      <AnimatePresence initial={false}>
        {compact && !editing && hovered && task.subtasks.length > 0 && (
          <motion.ul
            className="compact-subtask-list"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
          >
            {task.subtasks.map((s) => (
              <li key={s.clientKey ?? s.id} className={s.done ? 'compact-subtask-row done' : 'compact-subtask-row'}>
                <input
                  type="checkbox"
                  className="task-done-checkbox small"
                  checked={s.done}
                  title="Mark complete"
                  onChange={() => toggleSubtask.mutate({ subtaskId: s.id, done: !s.done })}
                />
                <span className="compact-subtask-title">{s.text}</span>
                <span className="compact-row-due">{s.due_date ?? ''}</span>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>

      {/* The toggle button that used to live here permanently is now the
          "📋" pill in .task-reveal above (and clicking a task already opens
          this panel via focus, see the effect syncing subtasksOpen to
          `focused`) - this section is just the panel itself now. */}
      {!compact && <div className="subtask-section">
        {subtasksOpen && (
          <div className="subtask-panel">
            <ul className="subtask-list">
              <AnimatePresence>
                {task.subtasks.map((s) => (
                  <motion.li
                    key={s.clientKey ?? s.id}
                    layout
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2, ease: 'easeOut' }}
                    className={[
                      'subtask-row',
                      s.done && 'done',
                      focusedSubtaskId === s.id && 'focused',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                  >
                    <span className="subtask-row-text" data-subtask-content-id={s.id}>
                      {s.text}
                      {s.due_date && (
                        <span
                          className={
                            !s.done && s.due_date < todayIso ? 'badge overdue subtask-due-badge' : 'badge subtask-due-badge'
                          }
                        >
                          {s.due_date}
                        </span>
                      )}
                      {s.notes && focusedSubtaskId !== s.id && (
                        <span className="notes-indicator" title="Has notes">
                          📝
                        </span>
                      )}
                    </span>
                    <button
                      type="button"
                      className={s.due_date ? 'icon-btn btn-primary' : 'icon-btn'}
                      aria-pressed={dueDatePickerSubtaskId === s.id}
                      title="Set due date"
                      onClick={() =>
                        setDueDatePickerSubtaskId((prev) => (prev === s.id ? null : s.id))
                      }
                    >
                      📅
                    </button>
                    {dueDatePickerSubtaskId === s.id && (
                      <DateInput
                        className="due-date-quick-input"
                        value={s.due_date ?? ''}
                        autoFocus
                        onCommit={(next) => {
                          setDueDatePickerSubtaskId(null)
                          if (next === (s.due_date ?? '')) return
                          setSubtaskDueDate.mutate({ subtaskId: s.id, dueDate: next || null })
                        }}
                      />
                    )}
                    {s.due_date && (
                      <button
                        type="button"
                        className="icon-btn"
                        title="Clear due date"
                        onClick={() => {
                          setDueDatePickerSubtaskId((prev) => (prev === s.id ? null : prev))
                          setSubtaskDueDate.mutate({ subtaskId: s.id, dueDate: null })
                        }}
                      >
                        ✕
                      </button>
                    )}
                    <button
                      type="button"
                      className={s.urgent ? 'icon-btn btn-primary' : 'icon-btn'}
                      aria-pressed={s.urgent}
                      title={s.urgent ? 'Unmark urgent' : 'Mark urgent'}
                      onClick={() => setSubtaskUrgent.mutate({ subtaskId: s.id, urgent: !s.urgent })}
                    >
                      🔥
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => toggleSubtask.mutate({ subtaskId: s.id, done: !s.done })}
                    >
                      {s.done ? '↩️' : '✔️'}
                    </button>
                    <button type="button" className="icon-btn" onClick={() => deleteSubtask.mutate(s.id)}>
                      🗑️
                    </button>
                    <AnimatePresence mode="popLayout">
                      {focusedSubtaskId === s.id && (
                        <motion.button
                          type="button"
                          className="subtask-notepad-toggle-btn"
                          initial={{ opacity: 0, y: -6, scale: 0.92 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: -6, scale: 0.92 }}
                          transition={{ type: 'spring', stiffness: 400, damping: 26 }}
                          onClick={() => onToggleNotepad?.()}
                        >
                          {notepadHidden ? '📝 Show notepad' : '📝 Hide notepad'}
                        </motion.button>
                      )}
                    </AnimatePresence>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
            <form className="subtask-add-form" onSubmit={submitSubtask}>
              <input
                id={`subtask-input-${task.id}`}
                placeholder="Add a subtask... (Press '/' to focus)"
                value={newSubtaskText}
                onChange={(e) => setNewSubtaskText(e.target.value)}
                onPaste={handleSubtaskPaste}
              />
              <button type="submit" className="btn-primary">
                Add
              </button>
            </form>
          </div>
        )}
      </div>}

      {/* Same as the subtask panel above - the "📝" icon in .task-reveal is
          now the toggle; this is just the panel. */}
      {!compact && (
        <div className="notes-section">
          {notesOpen && (
            <div
              ref={notesField.ref}
              className="notes-textarea rich-text-input"
              contentEditable
              suppressContentEditableWarning
              data-placeholder="Notes..."
              onInput={notesField.onInput}
              onFocus={notesField.onFocus}
              onBlur={notesField.onBlur}
              onKeyDown={notesField.onKeyDown}
            />
          )}
        </div>
      )}
    </>
  )

  const className = `task-card${task.done ? ' done' : ''}${focused ? ' focused' : ''}${justCompleted ? ' just-completed' : ''}${compact ? ' compact' : ''}${highlighted ? ' highlighted' : ''}`

  if (draggable) {
    return (
      <Reorder.Item
        value={task}
        dragListener={false}
        dragControls={dragControls}
        layout
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, height: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0, overflow: 'hidden' }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
        data-task-id={task.id}
        data-priority={task.priority}
        className={className}
        onDragEnd={() => onDragEnd?.(task.id)}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {content}
      </Reorder.Item>
    )
  }

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0, overflow: 'hidden' }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      data-task-id={task.id}
      data-priority={task.priority}
      className={className}
    >
      {content}
    </motion.li>
  )
}
