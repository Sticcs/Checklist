import { useState } from 'react'
import { useLists } from '../hooks/useLists'
import { useAddTask, useTasks } from '../hooks/useTasks'
import { VignetteOverlay } from './VignetteOverlay'

interface Props {
  targetListId: number
  onClose: () => void
}

// The expiry checklist's "Add from another list" picker - deliberately
// simple (per the request): pick a source list, click a task or one of its
// subtasks, it's copied in as a brand-new top-level task by text alone (no
// link/reference back to the source, no backend endpoint beyond the
// existing POST /tasks). Source items are left untouched.
export function AddFromListModal({ targetListId, onClose }: Props) {
  const { data: listsData } = useLists()
  const { data: tasksData } = useTasks()
  const addTask = useAddTask()
  const [sourceListId, setSourceListId] = useState<number | null>(null)
  const [justAddedKey, setJustAddedKey] = useState<string | null>(null)

  // Shopping/Assessments have different item shapes and panels, and other
  // expiry lists are excluded too (this picker is for pulling from "my
  // regular lists", not list-to-list copying in general).
  const sourceLists = (listsData?.lists ?? []).filter(
    (l) => (l.kind === 'main' || l.kind === 'custom') && l.id !== targetListId
  )

  const sourceTasks = sourceListId === null ? [] : (tasksData?.tasks ?? []).filter((t) => t.list_id === sourceListId)

  const copyIn = (text: string, key: string) => {
    addTask.mutate(
      { text, priority: 'Medium', category: 'General', dueDate: null, listId: targetListId },
      {
        onSuccess: () => {
          setJustAddedKey(key)
          window.setTimeout(() => setJustAddedKey((k) => (k === key ? null : k)), 1200)
        },
      }
    )
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
                <button type="button" className="add-from-list-row" onClick={() => copyIn(t.text, `task-${t.id}`)}>
                  {justAddedKey === `task-${t.id}` ? '✓ Added' : `📝 ${t.text}`}
                </button>
                {t.subtasks.length > 0 && (
                  <ul className="add-from-list-subitems">
                    {t.subtasks.map((s) => (
                      <li key={s.id}>
                        <button
                          type="button"
                          className="add-from-list-row"
                          onClick={() => copyIn(s.text, `subtask-${s.id}`)}
                        >
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
