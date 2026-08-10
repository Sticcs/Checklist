// Mirrors backend/app/models.py field-for-field.

export interface User {
  username: string
  is_guest: boolean
}

export interface Subtask {
  id: number
  task_id: number
  text: string
  done: boolean
  created_at: string
  urgent: boolean
  due_date: string | null
  notes: string | null
  // Client-only, never sent by the server: set on an optimistically-inserted
  // subtask and carried forward when its temp id is swapped for the real
  // one, so the React key stays stable across that swap instead of
  // triggering an unmount/remount (which replayed the enter/exit animation
  // as a visible flicker).
  clientKey?: string
}

export interface Task {
  id: number
  text: string
  done: boolean
  priority: string
  category: string
  due_date: string | null
  created_at: string
  username: string
  pinned: boolean
  position: number
  notes: string | null
  urgent: boolean
  subtasks: Subtask[]
  clientKey?: string
}

export interface TasksResponse {
  tasks: Task[]
  can_undo: boolean
  can_redo: boolean
}

export interface DailyCount {
  date: string
  count: number
}

export interface StatsResponse {
  current_streak: number
  longest_streak: number
  completed_today: number
  completed_this_week: number
  total_completed: number
  daily_counts: DailyCount[]
}

export interface MarkAllCompletedResponse {
  updated_count: number
}

export interface ClearResponse {
  deleted_count: number
}

export interface SubtaskMutationResponse {
  subtask: Subtask | null
  parent_done: boolean
}

export interface ActivityEntry {
  id: number
  action: string
  detail: string
  created_at: string
}
