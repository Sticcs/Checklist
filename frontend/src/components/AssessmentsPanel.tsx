import { AnimatePresence } from 'framer-motion'
import type { Task } from '../types'
import { AssessmentCard } from './AssessmentCard'

interface Props {
  assessments: Task[]
  focusedTaskId: number | null
  todayIso: string
}

export function AssessmentsPanel({ assessments, focusedTaskId, todayIso }: Props) {
  return (
    <div className="assessments-panel">
      <p className="assessments-heading">Assessments</p>
      <ul className="assessments-list">
        <AnimatePresence>
          {assessments.map((task) => (
            <AssessmentCard
              key={task.clientKey ?? task.id}
              task={task}
              focused={focusedTaskId === task.id}
              todayIso={todayIso}
            />
          ))}
        </AnimatePresence>
      </ul>
      {assessments.length === 0 && <p className="status-message">No assessments yet.</p>}
    </div>
  )
}
