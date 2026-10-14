import { useState } from 'react'
import { useLists } from '../hooks/useLists'
import { useAddTask, useTasks } from '../hooks/useTasks'
import { useAddSubtask } from '../hooks/useSubtasks'
import type { Subtask, Task } from '../types'
import { VignetteOverlay } from './VignetteOverlay'

interface Props {
  targetListId: number
  onClose: () => void
}

// The expiry checklist's "Add from another list" picker - deliberately
// simple (per the request): pick a source list, click a task or one of its
// subtasks to copy it in. A copied task is linked back to its source (see
// Task.linked_task_id) - checking either one off checks off the other, see
// useAddTask/useToggleDone's linked-propagation logic. A copied subtask
// brings its parent task along too (as a fresh, unlinked copy) so it isn't
// left floating with no context - only the subtask itself is linked back to
// its source.
export function AddFromListModal({ targetListId, onClose }: Props) {
  const { data: listsData } = useLists()
  const { data: tasksData } = useTasks()
  const addTask = useAddTask()
  const addSubtask = useAddSubtask()
  const [sourceListId, setSourceListId] = useState<number | null>(null)
  const [justAddedKey, setJustAddedKey] = useState<string | null>(null)

  // Shopping/Assessments have different item shapes and panels, and other
  // expiry lists are excluded too (this picker is for pulling from "my
  // regular lists", not list-to-list copying in general).
  const sourceLists = (listsData?.lists ?? []).filter(
    (l) => (l.kind === 'main' || l.kind === 'custom') && l.id !== targetListId
  )

  const sourceTasks = sourceListId === null ? [] : (tasksData?.tasks ?? []).filter((t) => t.list_id === sourceListId)

  const flashAdded = (key: string) => {
    setJustAddedKey(key)
    window.setTimeout(() => setJustAddedKey((k) => (k === key ? null : k)), 1200)
  }

  const copyTask = async (task: Task) => {
    const key = `task-${task.id}`
    try {
      await addTask.mutateAsync({
        text: task.text,
        priority: 'Medium',
        category: 'General',
        dueDate: null,
        listId: targetListId,
        linkedTaskId: task.id,
      })
      flashAdded(key)
    } catch {
      // Already surfaced via the hook's own onError toast.
    }
  }

  const copySubtask = async (parentTask: Task, subtask: Subtask) => {
    const key = `subtask-${subtask.id}`
    try {
      // The subtask needs a real task id to attach to, so the parent copy
      // has to land first. Chained via mutateAsync/await rather than a
      // call-level onSuccess callback - this component (and its onClose,
      // see the "Done" button below) can unmount the instant the first
      // part lands, since nothing here blocks that. A callback chained
      // through .mutate()'s options silently never fired once that
      // happened, dropping the subtask entirely; a plain awaited promise
      // chain keeps running regardless of whether this component is still
      // mounted to see it finish.
      const newTask = await addTask.mutateAsync({
        text: parentTask.text,
        priority: 'Medium',
        category: 'General',
        dueDate: null,
        listId: targetListId,
      })
      await addSubtask.mutateAsync({ taskId: newTask.id, text: subtask.text, linkedSubtaskId: subtask.id })
      flashAdded(key)
    } catch {
      // Already surfaced via the hooks' own onError toasts.
    }
  }

  return (
    <VignetteOverlay onCancel={onClose}>
      <div className="option-row">
        <div className="option-row-header">
          <p className="option-row-label">Add from another list</p>
        </div>
        <select
          className="custom-input"
          value={sourceListId ?? ''}
          onChange={(e) => setSourceListId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Choose a list...</option>
          {sourceLists.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>

        {sourceListId !== null && (
          <ul className="add-from-list-items">
            {sourceTasks.length === 0 && <p className="status-message">No tasks in this list.</p>}
            {sourceTasks.map((t) => (
              <li key={t.id}>
                <button type="button" className="add-from-list-row" onClick={() => copyTask(t)}>
                  {justAddedKey === `task-${t.id}` ? '✓ Added' : `📝 ${t.text}`}
                </button>
                {t.subtasks.length > 0 && (
                  <ul className="add-from-list-subitems">
                    {t.subtasks.map((s) => (
                      <li key={s.id}>
                        <button type="button" className="add-from-list-row" onClick={() => copySubtask(t, s)}>
                          {justAddedKey === `subtask-${s.id}` ? '✓ Added' : `↳ ${s.text}`}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}

        <div className="option-row-buttons">
          <button type="button" className="btn-primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </VignetteOverlay>
  )
}
