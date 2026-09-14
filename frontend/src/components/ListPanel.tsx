import { AnimatePresence, motion } from 'framer-motion'
import type { ListEntry, Task } from '../types'
import { useAddTask, useDeleteTask, useToggleDone } from '../hooks/useTasks'
import { LIST_ITEM_CATEGORY, SHOPPING_CATEGORY } from '../constants'
import { useDraftText } from '../hooks/useDraftText'
import { ListMenu } from './ListMenu'

interface Props {
  list: ListEntry
  items: Task[]
}

// The bare check+text UI for a "simple" list (see lists_table's is_simple
// comment) - always used for Shopping, and for any main/custom list a user
// has converted to simple via ListMenu's toggle. A "rich" list instead
// renders through TaskListPage's own TaskCard-based section directly.
export function ListPanel({ list, items }: Props) {
  const toggleDone = useToggleDone()
  const deleteTask = useDeleteTask()
  const addTask = useAddTask()

  // Keyed per-list so a draft in one list's add-item box doesn't bleed into
  // another's, and survives a reload the same way the main quick-add does.
  const [newItemText, setNewItemText] = useDraftText(`list-item:${list.id}`)

  const submitItem = (e: React.FormEvent) => {
    e.preventDefault()
    const text = newItemText.trim()
    if (!text) return
    setNewItemText('')
    if (list.kind === 'shopping') {
      addTask.mutate({ text, priority: 'Medium', category: SHOPPING_CATEGORY, dueDate: null })
    } else {
      addTask.mutate({ text, priority: 'Medium', category: LIST_ITEM_CATEGORY, dueDate: null, listId: list.id })
    }
  }

  return (
    <div className="assessments-panel">
      <ListMenu list={list} items={items} />

      <form className="assignment-task-add-form" onSubmit={submitItem}>
        <input
          placeholder="Add an item..."
          value={newItemText}
          onChange={(e) => setNewItemText(e.target.value)}
        />
      </form>

      <ul className="shopping-list">
        <AnimatePresence>
          {items.map((item) => (
            <motion.li
              key={item.clientKey ?? item.id}
              layout
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0, overflow: 'hidden' }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className={item.done ? 'shopping-item done' : 'shopping-item'}
            >
              <input
                type="checkbox"
                className="task-done-checkbox"
                checked={item.done}
                title="Mark done"
                onChange={() => toggleDone.mutate({ id: item.id, done: !item.done })}
              />
              <span className={item.done ? 'task-text done' : 'task-text'}>{item.text}</span>
              <button
                type="button"
                className="icon-btn"
                title="Remove from list"
                onClick={() => deleteTask.mutate(item.id)}
              >
                🗑️
              </button>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
      {items.length === 0 && <p className="status-message">No items yet.</p>}
    </div>
  )
}
