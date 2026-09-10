import { AnimatePresence, motion } from 'framer-motion'
import type { Task } from '../types'
import { AssessmentCard } from './AssessmentCard'

interface Props {
  assessments: Task[]
  // Assignments shared with (not owned by) this user - see TaskListPage's
  // useSharedWithMe. Deliberately rendered as a much simpler, read-mostly
  // list below the owned assessments: no edit/delete/urgent icons, no
  // Alt+click-assign selection - all real interaction happens once you're
  // inside the workspace itself (see AssignmentWorkspace).
  shared: Task[]
  focusedTaskId: number | null
  todayIso: string
  selectedAssessmentId: number | null
  highlightedAssessmentIds: Set<number>
  onStart: (taskId: number) => void
  onOpenShared: (taskId: number) => void
  onShowParentTask: (taskId: number) => void
  compact?: boolean
}

export function AssessmentsPanel({
  assessments,
  shared,
  focusedTaskId,
  todayIso,
  selectedAssessmentId,
  highlightedAssessmentIds,
  onStart,
  onOpenShared,
  onShowParentTask,
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
              onShowParentTask={onShowParentTask}
              compact={compact}
            />
          ))}
        </AnimatePresence>
      </ul>
      {assessments.length === 0 && <p className="status-message">No assessments yet.</p>}

      {shared.length > 0 && (
        <>
          <p className="assessments-heading shared-heading">🤝 Shared with me</p>
          <ul className="assessments-list shared-assessments-list">
            <AnimatePresence>
              {shared.map((task) => (
                <motion.li
                  key={task.id}
                  layout
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0, overflow: 'hidden' }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                  className={task.done ? 'assessment-card shared done' : 'assessment-card shared'}
                >
                  <button
                    type="button"
                    className="shared-assessment-open-btn"
                    onClick={() => onOpenShared(task.id)}
                  >
                    <span className={task.done ? 'task-text done' : 'task-text'}>{task.text}</span>
                    <span className="shared-assessment-owner">by {task.username}</span>
                  </button>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        </>
      )}
    </div>
  )
}
