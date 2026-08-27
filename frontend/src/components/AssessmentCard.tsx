import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import type { Task } from '../types'
import { PRIORITIES } from '../constants'
import { useDeleteTask, useEditTask, useSetTaskUrgent, useToggleDone } from '../hooks/useTasks'
import { daysUntil } from '../utils/dueDatePresets'
import { DateInput } from './DateInput'

interface Props {
  task: Task
  // Doubles as "selected for Alt+click assignment" (see TaskListPage) - a
  // plain click on an assessment already focuses it via the existing
  // document-level click delegation (same mechanism as any other task
  // card), so a focused assessment specifically just *is* the one that's
  // selected. No separate selection state or click handler needed.
  focused: boolean
  todayIso: string
  highlighted: boolean
  onStart: (taskId: number) => void
  compact?: boolean
}

// A trimmed-down sibling of TaskCard for the Assessments panel: same
// underlying entity and the same optimistic mutations (so ctrl+click,
// undo/redo, and Clear completed all just work), but no subtasks, no
// pinning, and a much smaller footprint - text, due date, priority color,
// urgent toggle, edit, delete.
export function AssessmentCard({ task, focused, todayIso, highlighted, onStart, compact = false }: Props) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(task.text)
  const [editPriority, setEditPriority] = useState(task.priority)
  const [editDueDate, setEditDueDate] = useState(task.due_date ?? '')

  const toggleDone = useToggleDone()
  const editTask = useEditTask()
  const deleteTask = useDeleteTask()
  const setTaskUrgent = useSetTaskUrgent()

  const overdue = !!task.due_date && !task.done && task.due_date < todayIso
  const daysToDue = task.due_date ? daysUntil(task.due_date, todayIso) : null
  // The assignment workspace's textbox writes back to this same notes
  // field - non-empty means the user has already put something down there,
  // so the button should read "Continue" rather than "Start" over it.
  const hasStarted = Boolean(task.notes && task.notes.trim().length > 0)

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

  const startEditing = () => {
    setEditText(task.text)
    setEditPriority(task.priority)
    setEditDueDate(task.due_date ?? '')
    setEditing(true)
  }

  const saveEdit = (e: React.FormEvent) => {
    e.preventDefault()
    setEditing(false)
    editTask.mutate({
      id: task.id,
      text: editText.trim(),
      priority: editPriority,
      category: 'Assessment',
      dueDate: editDueDate || null,
    })
  }

  const className =
    `assessment-card${task.done ? ' done' : ''}${focused ? ' focused' : ''}` +
    `${justCompleted ? ' just-completed' : ''}${highlighted ? ' highlighted' : ''}${compact ? ' compact' : ''}`

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0, overflow: 'hidden' }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      data-task-id={task.id}
      data-priority={task.priority}
      className={className}
    >
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
            className={task.urgent ? 'compact-star-btn pinned' : 'compact-star-btn'}
            aria-pressed={task.urgent}
            title={task.urgent ? 'Unmark urgent' : 'Mark urgent (important)'}
            onClick={() => setTaskUrgent.mutate({ id: task.id, urgent: !task.urgent })}
          >
            {task.urgent ? '★' : '☆'}
          </button>
          <div className="compact-row-actions" ref={compactMenuRef}>
            <button
              type="button"
              className="compact-menu-btn"
              aria-expanded={compactMenuOpen}
              title="More actions"
              onClick={(e) => {
                e.stopPropagation()
                setCompactMenuOpen((open) => !open)
              }}
            >
              ⋮
            </button>
            {compactMenuOpen && (
              <div className="compact-menu-popover" data-focus-exempt>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setCompactMenuOpen(false)
                    onStart(task.id)
                  }}
                >
                  {hasStarted ? '⏵ Continue' : '▶ Start'}
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
        <div data-task-content-id={task.id} className="assessment-content">
          <input
            type="checkbox"
            className="task-done-checkbox"
            checked={task.done}
            title="Mark complete"
            onChange={() => toggleDone.mutate({ id: task.id, done: !task.done })}
          />
          <div className="assessment-main">
            <span className={task.done ? 'task-text done' : 'task-text'}>{task.text}</span>
            {task.due_date && (
              <span className={overdue ? 'badge overdue' : 'badge'}>
                {task.due_date}
                {daysToDue !== null && !task.done && (
                  <>
                    {' '}
                    (
                    {daysToDue < 0
                      ? `${Math.abs(daysToDue)} day${Math.abs(daysToDue) === 1 ? '' : 's'} overdue`
                      : daysToDue === 0
                        ? 'due today'
                        : `due in ${daysToDue} day${daysToDue === 1 ? '' : 's'}`}
                    )
                  </>
                )}
              </span>
            )}
            {task.urgent && <span className="urgent-badge">🚨 Urgent</span>}
            {task.in_progress && !task.done && (
              <span className="in-progress-badge">🚧 In progress</span>
            )}
          </div>
          <div className="assessment-actions">
            {focused && (
              <button
                type="button"
                className="btn-start"
                title={hasStarted ? 'Continue working on this assessment' : 'Start working on this assessment'}
                onClick={(e) => {
                  // Otherwise bubbles up to the document-level click
                  // delegation (see TaskListPage) and toggles this card's
                  // focus off in the same click that's meant to open the
                  // workspace.
                  e.stopPropagation()
                  onStart(task.id)
                }}
              >
                {hasStarted ? '⏵ Continue' : '▶ Start'}
              </button>
            )}
            <button
              type="button"
              className={task.urgent ? 'icon-btn btn-primary' : 'icon-btn'}
              aria-pressed={task.urgent}
              title={task.urgent ? 'Unmark urgent' : 'Mark urgent'}
              onClick={() => setTaskUrgent.mutate({ id: task.id, urgent: !task.urgent })}
            >
              🔥
            </button>
            <button type="button" className="icon-btn" onClick={startEditing}>
              ✏️
            </button>
            <button type="button" className="icon-btn" onClick={() => deleteTask.mutate(task.id)}>
              🗑️
            </button>
          </div>
        </div>
      )}
    </motion.li>
  )
}
