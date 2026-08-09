import type { Task } from '../types'
import { PRIORITY_ORDER } from '../constants'

export type SortBy = 'Priority' | 'Due date' | 'Newest first'

// Direct port of main.py's filter/sort chain. JS's Array.sort is stable
// (guaranteed since ES2019), same as Python's, so this multi-pass approach
// works identically: each pass only breaks ties left by the previous one.
export function sortTasks(tasks: Task[], sortBy: SortBy): Task[] {
  const sorted = [...tasks]

  if (sortBy === 'Priority') {
    sorted.sort((a, b) => (PRIORITY_ORDER[a.priority] ?? 3) - (PRIORITY_ORDER[b.priority] ?? 3))
  } else if (sortBy === 'Due date') {
    sorted.sort((a, b) => {
      if (a.due_date === null && b.due_date === null) return 0
      if (a.due_date === null) return 1
      if (b.due_date === null) return -1
      return a.due_date.localeCompare(b.due_date)
    })
  }
  // "Newest first" needs no pass here - the backend already returns tasks
  // ordered by created_at DESC, and that order survives as the tiebreaker
  // within each done/pinned group below.

  // Completed tasks float to the top of whatever secondary sort was chosen
  // above, and pinned tasks float above *those*.
  sorted.sort((a, b) => Number(!a.done) - Number(!b.done))
  sorted.sort((a, b) => Number(!a.pinned) - Number(!b.pinned))

  return sorted
}
