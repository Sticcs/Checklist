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
  subtasks: Subtask[]
}

export interface TasksResponse {
  tasks: Task[]
  can_undo: boolean
  can_redo: boolean
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
