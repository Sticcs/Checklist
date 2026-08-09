import { motion } from 'framer-motion'

interface Props {
  done: number
  total: number
}

export function ProgressBar({ done, total }: Props) {
  if (total === 0) return null
  const pct = total === 0 ? 0 : (done / total) * 100

  return (
    <div className="progress-bar">
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
    </div>
  )
}
