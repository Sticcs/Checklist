import { AnimatePresence, motion } from 'framer-motion'
import type { Task } from '../types'
import { AssessmentCard } from './AssessmentCard'

interface Props {
  assessments: Task[]
  focusedTaskId: number | null
  todayIso: string
  selectedAssessmentId: number | null
  highlightedAssessmentIds: Set<number>
  onStart: (taskId: number) => void
  compact?: boolean
}

export function AssessmentsPanel({
  assessments,
  focusedTaskId,
  todayIso,
  selectedAssessmentId,
  highlightedAssessmentIds,
  onStart,
  compact = false,
}: Props) {
  return (
    <div className="assessments-panel">
      <p className="assessments-heading">Assessments</p>
      <AnimatePresence>
        {selectedAssessmentId !== null && (
          <motion.p
            className="assign-hint"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.15 }}
          >
            ⌥ Alt + click a task in the list to assign under it
          </motion.p>
        )}
      </AnimatePresence>
      {compact && assessments.length > 0 && (
        <div className="compact-row compact-header-row">
          <span className="compact-header-checkbox-spacer" />
          <span className="compact-row-title">Title</span>
          <span className="compact-row-due">Due Date</span>
          <span className="compact-star-btn">Importance</span>
          <span className="compact-row-actions" />
        </div>
      )}
      <ul className="assessments-list">
        <AnimatePresence>
          {assessments.map((task) => (
            <AssessmentCard
              key={task.clientKey ?? task.id}
              task={task}
              focused={focusedTaskId === task.id}
              todayIso={todayIso}
              highlighted={highlightedAssessmentIds.has(task.id)}
              onStart={onStart}
              compact={compact}
            />
          ))}
        </AnimatePresence>
      </ul>
      {assessments.length === 0 && <p className="status-message">No assessments yet.</p>}
    </div>
  )
}
