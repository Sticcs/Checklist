import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, Reorder, useDragControls } from 'framer-motion'
import type { Task } from '../types'
import { CATEGORIES, PRIORITIES } from '../constants'
import { useSettings } from '../context/SettingsContext'
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
import { DateInput } from './DateInput'

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
}: Props) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(task.text)
  const [editPriority, setEditPriority] = useState(task.priority)
  const [editCategory, setEditCategory] = useState(task.category)
  const [editDueDate, setEditDueDate] = useState(task.due_date ?? '')

  const [subtasksOpen, setSubtasksOpen] = useState(false)
  const [newSubtaskText, setNewSubtaskText] = useState('')

  const [notesOpen, setNotesOpen] = useState(false)
  const [notesDraft, setNotesDraft] = useState(task.notes ?? '')
  const notesDirty = useRef(false)

  const [dueDatePickerSubtaskId, setDueDatePickerSubtaskId] = useState<number | null>(null)

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
  const subtaskDueTallyLabel = (d: number): string =>
    d < 0
      ? `${Math.abs(d)} day${Math.abs(d) === 1 ? '' : 's'} overdue`
      : d === 0
        ? 'due today'
        : `due in ${d} day${d === 1 ? '' : 's'}`

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

  useEffect(() => {
    if (!notesDirty.current) return
    const handle = setTimeout(() => {
      notesDirty.current = false
      setTaskNotes.mutate({ id: task.id, notes: notesDraft })
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, 600)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notesDraft])

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
    setNotesDraft(value)
  }

  const startEditing = () => {
    setEditText(task.text)
    setEditPriority(task.priority)
    setEditCategory(task.category)
    setEditDueDate(task.due_date ?? '')
    setEditing(true)
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
      ) : (
        <div data-task-content-id={task.id} className="task-content">
          <div className="task-title">
            {draggable && (
              <span
                className="drag-handle"
                title="Drag to reorder"
                onPointerDown={(e) => dragControls.start(e)}
              >
                ⠿
              </span>
            )}
            {task.pinned && (
              <span className="pin-badge" title="Pinned">
                📌
              </span>
            )}
            <span className={task.done ? 'task-text done' : 'task-text'}>{task.text}</span>
            {dueUrgent && <span className="urgent-badge">🚨 Urgent!</span>}
            {dueSoon && (
              <span className="due-soon-badge">⏳ Due in {daysToDue} day{daysToDue === 1 ? '' : 's'}</span>
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
                    📅 {count} {subtaskDueTallyLabel(d)}
                  </span>
                ))}
              </div>
            )}
            {!notesOpen && task.notes && (
              <span className="notes-indicator" title="Has notes">
                📝
              </span>
            )}
          </div>
          <div className="meta-tags">
            <span className="badge">{task.category}</span>
            {task.due_date && <span className={overdue ? 'badge overdue' : 'badge'}>{task.due_date}</span>}
          </div>
          {task.subtasks.length > 0 && (
            <div className="subtask-progress-wrap">
              <div className="progress-bar-track small">
                <motion.div
                  className="progress-bar-fill"
                  initial={false}
                  animate={{ width: `${(subDone / task.subtasks.length) * 100}%` }}
                  transition={{ duration: 0.3, ease: 'easeOut' }}
                />
              </div>
              <span className="subtask-progress-label">
                Subtasks: {subDone}/{task.subtasks.length}
              </span>
            </div>
          )}
        </div>
      )}

      <div className="task-actions">
        {!editing && (
          <input
            type="checkbox"
            className="task-done-checkbox"
            checked={task.done}
            title="Mark complete"
            onChange={() => toggleDone.mutate({ id: task.id, done: !task.done })}
          />
        )}
        <button
          type="button"
          className={task.pinned ? 'icon-btn btn-primary' : 'icon-btn'}
          aria-pressed={task.pinned}
          onClick={() => setPinned.mutate({ id: task.id, pinned: !task.pinned })}
        >
          📌
        </button>
        {!editing && (
          <button type="button" className="icon-btn" onClick={startEditing}>
            ✏️
          </button>
        )}
        <button type="button" className="icon-btn" onClick={() => deleteTask.mutate(task.id)}>
          🗑️
        </button>
      </div>

      <div className="subtask-section">
        <button type="button" className="subtask-toggle-btn" onClick={toggleSubtasksOpen}>
          {task.subtasks.length > 0
            ? `📋 Subtasks (${subDone}/${task.subtasks.length})`
            : '📋 Add subtasks'}
        </button>
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
                    <AnimatePresence>
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
              />
              <button type="submit" className="btn-primary">
                Add
              </button>
            </form>
          </div>
        )}
      </div>

      <div className="notes-section">
        <button
          type="button"
          className="subtask-toggle-btn"
          onClick={() => setNotesOpen((prev) => !prev)}
        >
          {task.notes ? '📝 Notes' : '📝 Add notes'}
        </button>
        {notesOpen && (
          <textarea
            className="notes-textarea"
            placeholder="Notes..."
            value={notesDraft}
            onChange={(e) => handleNotesChange(e.target.value)}
          />
        )}
      </div>
    </>
  )

  const className = `task-card${task.done ? ' done' : ''}${focused ? ' focused' : ''}${justCompleted ? ' just-completed' : ''}`

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
      data-task-id={task.id}
      data-priority={task.priority}
      className={className}
    >
      {content}
    </motion.li>
  )
}
