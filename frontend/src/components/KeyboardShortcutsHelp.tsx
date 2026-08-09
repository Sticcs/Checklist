import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { isTypingElement } from '../utils/isTypingElement'

interface ShortcutRow {
  keys: string[]
  description: string
}

interface ShortcutGroup {
  title: string
  rows: ShortcutRow[]
}

const GROUPS: ShortcutGroup[] = [
  {
    title: 'Anywhere',
    rows: [
      { keys: ['?'], description: 'Show this shortcuts list' },
      { keys: ['`'], description: 'Focus the scratchpad' },
      { keys: ['/'], description: 'Focus a subtask input (or the main task input)' },
      { keys: ['Ctrl', 'Click'], description: 'Toggle a task complete' },
      { keys: ['Ctrl', 'Z'], description: 'Undo' },
      { keys: ['Ctrl', 'Shift', 'Z'], description: 'Redo' },
      { keys: ['Ctrl', 'Y'], description: 'Redo' },
    ],
  },
  {
    title: 'Adding a task (after pressing Enter to lock in the text)',
    rows: [
      { keys: ['H'], description: 'Category: House' },
      { keys: ['W'], description: 'Category: Work' },
      { keys: ['S'], description: 'Category: Study' },
      { keys: ['P'], description: 'Category: Personal' },
      { keys: ['A'], description: 'Category: Assessment' },
      { keys: ['C'], description: 'Category: Custom' },
      { keys: ['T'], description: 'Priority: High' },
      { keys: ['M'], description: 'Priority: Medium' },
      { keys: ['L'], description: 'Priority: Low' },
      { keys: ['1'], description: 'Due: Today' },
      { keys: ['2'], description: 'Due: Tomorrow' },
      { keys: ['3'], description: 'Due: This week' },
      { keys: ['4'], description: 'Due: Next week' },
      { keys: ['5'], description: 'Due: Custom' },
      { keys: ['6'], description: 'Due: No date' },
      { keys: ['Enter'], description: 'Confirm the current step / add the task' },
    ],
  },
  {
    title: 'Date fields',
    rows: [
      { keys: ['Enter'], description: 'Save the date' },
      { keys: ['Esc'], description: 'Close without changing anything unsaved' },
    ],
  },
]

export function KeyboardShortcutsHelp() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '?' && !isTypingElement(document.activeElement)) {
        e.preventDefault()
        setOpen((prev) => !prev)
      } else if (e.key === 'Escape') {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  return (
    <>
      <button
        type="button"
        className="shortcuts-trigger"
        onClick={() => setOpen(true)}
        title="Keyboard shortcuts"
      >
        <kbd>?</kbd> Shortcuts
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="shortcuts-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setOpen(false)}
          >
            <motion.div
              className="shortcuts-modal"
              initial={{ opacity: 0, scale: 0.96, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="shortcuts-modal-header">
                <h2>Keyboard shortcuts</h2>
                <button type="button" className="icon-btn" onClick={() => setOpen(false)} title="Close">
                  ✕
                </button>
              </div>
              {GROUPS.map((group) => (
                <div key={group.title} className="shortcuts-group">
                  <p className="shortcuts-group-title">{group.title}</p>
                  <ul className="shortcuts-list">
                    {group.rows.map((row) => (
                      <li key={row.description} className="shortcuts-row">
                        <span className="shortcuts-keys">
                          {row.keys.map((k, i) => (
                            <span key={i}>
                              <kbd>{k}</kbd>
                              {i < row.keys.length - 1 && <span className="shortcuts-plus">+</span>}
                            </span>
                          ))}
                        </span>
                        <span className="shortcuts-desc">{row.description}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
