import type { Task } from '../types'
import { daysUntil, toISODate } from './dueDatePresets'

export interface DueTomorrowEntry {
  id: string
  text: string
  taskId: number
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
    if (!task.done && task.due_date && daysUntil(task.due_date, todayIso) === 1) {
      entries.push({ id: `t${task.id}`, text: task.text, taskId: task.id })
    }
    for (const subtask of task.subtasks) {
      if (!subtask.done && subtask.due_date && daysUntil(subtask.due_date, todayIso) === 1) {
        entries.push({ id: `s${subtask.id}`, text: subtask.text, taskId: task.id })
      }
    }
  }

  return entries
}
