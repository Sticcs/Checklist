import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

interface Props {
  title: string
  open: boolean
  onToggle: (open: boolean) => void
  children: ReactNode
}

// A framer-motion-driven replacement for a native <details>/<summary> pair -
// <details> only ever snaps open/closed with no animation hook available, so
// the "toggle" here is a plain button and the body's height animates through
// AnimatePresence instead.
export function CollapsibleSection({ title, open, onToggle, children }: Props) {
  return (
    <div className="collapsible-section">
      <button
        type="button"
        className="collapsible-summary"
        aria-expanded={open}
        onClick={() => onToggle(!open)}
      >
        <span className={open ? 'collapsible-caret open' : 'collapsible-caret'}>▸</span>
        {title}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: 'easeInOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div className="collapsible-body">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
