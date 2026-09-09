import { AnimatePresence, motion } from 'framer-motion'
import type { Task } from '../types'
import { useDeleteTask, useToggleDone } from '../hooks/useTasks'

interface Props {
  items: Task[]
}

// Deliberately minimal for now (per the request: "just add basic check and
// delete feature") - items themselves are added via the main AddTaskForm's
// Shopping category (see its fast-path there), same as how assessments are
// added via its Assessment category rather than from within
// AssessmentsPanel. No due date, priority, or notes shown here even though
// the underlying Task entity has them - just text, a checkbox, and delete.
export function ShoppingPanel({ items }: Props) {
  const toggleDone = useToggleDone()
  const deleteTask = useDeleteTask()

  return (
    <div className="assessments-panel">
      <p className="assessments-heading">Shopping list</p>
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
                title="Got it"
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
      {items.length === 0 && <p className="status-message">No shopping items yet.</p>}
    </div>
  )
}
