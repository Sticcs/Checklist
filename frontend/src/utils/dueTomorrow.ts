import type { Task } from '../types'
import { daysUntil, toISODate } from './dueDatePresets'
import { ASSESSMENT_CATEGORY } from '../constants'

export interface DueTomorrowEntry {
  id: string
  text: string
  taskId: number
  // Whether taskId points at an Assessment (opens the AssignmentWorkspace)
  // or a plain task (should just be highlighted/scrolled to in the main
  // list instead - opening the workspace for a non-assignment task would
  // show the wrong UI entirely).
  isAssignment: boolean
}

// Same "due tomorrow" condition useDueDateNotifications.ts already fires a
// one-shot browser Notification for, but as a plain list for the
// notification panel instead - no permission check, no per-day localStorage
// dedup, since this just reflects live state and naturally stops matching
// once the date passes or the item's done/rescheduled.
export function getDueTomorrowEntries(tasks: Task[]): DueTomorrowEntry[] {
  const todayIso = toISODate(new Date())
  const entries: DueTomorrowEntry[] = []

  for (const task of tasks) {
    const isAssignment = task.category === ASSESSMENT_CATEGORY
    if (!task.done && task.due_date && daysUntil(task.due_date, todayIso) === 1) {
      entries.push({ id: `t${task.id}`, text: task.text, taskId: task.id, isAssignment })
    }
    for (const subtask of task.subtasks) {
      if (!subtask.done && subtask.due_date && daysUntil(subtask.due_date, todayIso) === 1) {
        entries.push({ id: `s${subtask.id}`, text: subtask.text, taskId: task.id, isAssignment })
      }
    }
  }

  return entries
}
