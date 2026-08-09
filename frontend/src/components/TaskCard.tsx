import { useState } from 'react'
import { motion } from 'framer-motion'
import type { Task } from '../types'
import { CATEGORIES, PRIORITIES } from '../constants'
import { useDeleteTask, useEditTask, useSetPinned } from '../hooks/useTasks'
import { useAddSubtask, useDeleteSubtask, useToggleSubtask } from '../hooks/useSubtasks'

interface Props {
  task: Task
  focused: boolean
  todayIso: string
  onExpandSubtasks?: (taskId: number) => void
}

export function TaskCard({ task, focused, todayIso, onExpandSubtasks }: Props) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(task.text)
  const [editPriority, setEditPriority] = useState(task.priority)
  const [editCategory, setEditCategory] = useState(task.category)
  const [editDueDate, setEditDueDate] = useState(task.due_date ?? '')

  const [subtasksOpen, setSubtasksOpen] = useState(false)
  const [newSubtaskText, setNewSubtaskText] = useState('')

  const setPinned = useSetPinned()
  const editTask = useEditTask()
  const deleteTask = useDeleteTask()
  const addSubtask = useAddSubtask()
  const toggleSubtask = useToggleSubtask()
  const deleteSubtask = useDeleteSubtask()

  const overdue = !!task.due_date && !task.done && task.due_date < todayIso
  const urgent = task.due_date === todayIso && !task.done
  const subDone = task.subtasks.filter((s) => s.done).length

  const toggleSubtasksOpen = () => {
    const next = !subtasksOpen
    setSubtasksOpen(next)
    if (next) onExpandSubtasks?.(task.id)
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
    editTask.mutate(
      {
        id: task.id,
        text: editText.trim(),
        priority: editPriority,
        category: editCategory,
        dueDate: editDueDate || null,
      },
      { onSuccess: () => setEditing(false) }
    )
  }

  const submitSubtask = (e: React.FormEvent) => {
    e.preventDefault()
    const text = newSubtaskText.trim()
    if (!text) return
    addSubtask.mutate({ taskId: task.id, text }, { onSuccess: () => setNewSubtaskText('') })
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
      className={`task-card${task.done ? ' done' : ''}${focused ? ' focused' : ''}`}
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
            <select value={editCategory} onChange={(e) => setEditCategory(e.target.value)}>
              {CATEGORIES.filter((c) => c !== 'Custom').map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <input type="date" value={editDueDate} onChange={(e) => setEditDueDate(e.target.value)} />
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
            {task.pinned && (
              <span className="pin-badge" title="Pinned">
                📌
              </span>
            )}
            <span className={task.done ? 'task-text done' : 'task-text'}>{task.text}</span>
            {urgent && <span className="urgent-badge">🚨 Urgent!</span>}
          </div>
          <div className="meta-tags">
            <span className="badge">{task.category}</span>
            {task.due_date && <span className={overdue ? 'badge overdue' : 'badge'}>{task.due_date}</span>}
          </div>
          {task.subtasks.length > 0 && (
            <div className="subtask-progress-wrap">
              <div className="progress-bar-track small">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${(subDone / task.subtasks.length) * 100}%` }}
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
              {task.subtasks.map((s) => (
                <li key={s.id} className={s.done ? 'subtask-row done' : 'subtask-row'}>
                  <span>{s.text}</span>
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
                </li>
              ))}
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
    </motion.li>
  )
}
