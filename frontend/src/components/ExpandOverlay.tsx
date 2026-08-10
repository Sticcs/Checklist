import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'

interface Props {
  label: string
  onClose: () => void
  children: React.ReactNode
  accent?: boolean
}

// Rendered via a portal straight into <body>. The compact panel this expands
// from (.scratchpad / .subtask-notepad) can sit inside a framer-motion
// element carrying its own animated `transform` (see the wrapper around
// SubtaskNotepad in TaskListPage) - a `position: fixed` descendant of that
// would be confined to the transformed ancestor's box instead of the real
// viewport, so this sidesteps the whole ancestor chain instead of relying on
// none of them ever animating.
//
// Mount/unmount (not visibility) is what drives the exit animation, so the
// caller must wrap the conditional render in its own <AnimatePresence> -
// this component doesn't wrap itself in one.
export function ExpandOverlay({ label, onClose, children, accent }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return createPortal(
    <motion.div
      className="expand-overlay-backdrop"
      data-focus-exempt
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      onClick={onClose}
    >
      <motion.div
        className={accent ? 'expand-overlay-panel accent' : 'expand-overlay-panel'}
        initial={{ opacity: 0, scale: 0.9, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 16 }}
        transition={{ type: 'spring', stiffness: 300, damping: 28 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="expand-overlay-header">
          <p className="expand-overlay-label">{label}</p>
          <button type="button" className="icon-btn" onClick={onClose} title="Close (Esc)">
            ✕
          </button>
        </div>
        {children}
      </motion.div>
    </motion.div>,
    document.body
  )
}
