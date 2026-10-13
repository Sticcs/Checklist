import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'

// Rendered via a portal straight into <body> (same pattern as
// ExpandOverlay.tsx) - a modal's own DOM ancestor often has its own
// backdrop-filter (glass-panel styling), which - like transform/filter -
// establishes a new containing block for position:fixed descendants.
// Without the portal, this vignette's "inset: 0" would resolve against
// that small ancestor box instead of the actual viewport, confining the
// overlay to a tiny area overlapping whatever sat below it.
//
// Must be a genuine component (not createPortal() called inline as
// AnimatePresence's own child expression) - AnimatePresence needs a real,
// cloneable element as its direct child to track for exit animations; hand
// it a raw ReactPortal directly and it silently fails to render anything.
//
// Originally lived only in AddTaskForm.tsx (its own category/priority/
// due-date wizard) - extracted here so any other multi-step modal (see
// CreateListModal/AddFromListModal) can reuse the exact same overlay
// chrome instead of duplicating it.
export function VignetteOverlay({ onCancel, children }: { onCancel: () => void; children: React.ReactNode }) {
  return createPortal(
    <motion.div
      className="task-entry-vignette"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="task-entry-vignette-panel">{children}</div>
    </motion.div>,
    document.body
  )
}
