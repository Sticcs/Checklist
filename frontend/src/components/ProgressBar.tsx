import { AnimatePresence, motion } from 'framer-motion'

interface Props {
  done: number
  total: number
}

export function ProgressBar({ done, total }: Props) {
  const pct = total === 0 ? 0 : (done / total) * 100

  return (
    <AnimatePresence>
      {total > 0 && (
        <motion.div
          className="progress-bar"
          initial={{ opacity: 0, y: -8, height: 0 }}
          animate={{ opacity: 1, y: 0, height: 'auto' }}
          exit={{ opacity: 0, y: -8, height: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
        >
          <div className="progress-bar-label">
            {done} / {total} completed
          </div>
          <div className="progress-bar-track">
            <motion.div
              className="progress-bar-fill"
              initial={false}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
            />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
