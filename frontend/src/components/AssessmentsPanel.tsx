import { AnimatePresence, motion } from 'framer-motion'
import type { Task } from '../types'
import { AssessmentCard } from './AssessmentCard'

interface Props {
  assessments: Task[]
  focusedTaskId: number | null
  todayIso: string
  selectedAssessmentId: number | null
  highlightedAssessmentIds: Set<number>
}

export function AssessmentsPanel({
  assessments,
  focusedTaskId,
  todayIso,
  selectedAssessmentId,
  highlightedAssessmentIds,
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
      <ul className="assessments-list">
        <AnimatePresence>
          {assessments.map((task) => (
            <AssessmentCard
              key={task.clientKey ?? task.id}
              task={task}
              focused={focusedTaskId === task.id}
              todayIso={todayIso}
              highlighted={highlightedAssessmentIds.has(task.id)}
            />
          ))}
        </AnimatePresence>
      </ul>
      {assessments.length === 0 && <p className="status-message">No assessments yet.</p>}
    </div>
  )
}
