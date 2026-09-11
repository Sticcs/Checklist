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
  // Who this mini task (in an Assignment workspace's own bare-bones task
  // panel) is assigned to - the owner's own username, one of the
  // assignment's collaborators, or null for unassigned.
  assigned_username: string | null
  // Client-only, never sent by the server: set on an optimistically-inserted
  // subtask and carried forward when its temp id is swapped for the real
  // one, so the React key stays stable across that swap instead of
  // triggering an unmount/remount (which replayed the enter/exit animation
  // as a visible flicker).
  clientKey?: string
}

export interface LinkItem {
  name: string
  url: string
}

export interface WorkspacePage {
  id: string
  title: string
  content: string
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
  // Set on an assessment (category === 'Assessment') that's been Alt+click
  // assigned under this id (a plain task) - see TaskListPage's assignment
  // selection state and useAssignTask. Always null on the plain task itself.
  assigned_task_id: number | null
  // Set once "Start" has been clicked on this assessment (see
  // AssignmentWorkspace) - cleared again on completion.
  in_progress: boolean
  links: LinkItem[]
  pages: WorkspacePage[]
  subtasks: Subtask[]
  // Set for a task that's an item in a custom list (see ListEntry below) -
  // null for everything else, including Assessment/Shopping-category tasks
  // (which are still routed by category alone).
  list_id: number | null
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

export interface ExportedSubtask {
  text: string
  done: boolean
  urgent: boolean
  due_date: string | null
  notes: string | null
}

export interface ExportedTask {
  text: string
  priority: string
  category: string
  due_date: string | null
  done: boolean
  pinned: boolean
  urgent: boolean
  notes: string | null
  in_progress: boolean
  links: LinkItem[]
  pages: WorkspacePage[]
  subtasks: ExportedSubtask[]
}

export interface ExportPayload {
  version: number
  exported_at: string
  tasks: ExportedTask[]
}

export interface ImportResponse {
  imported_tasks: number
  imported_subtasks: number
}

export interface WebsiteLinkStatus {
  linked: boolean
  username: string | null
}

export interface ActivityEntry {
  id: number
  action: string
  detail: string
  created_at: string
}

export interface ShareLink {
  token: string
  url: string
}

export interface Collaborator {
  username: string
  added_at: string
}

// Shopping and user-created ("custom") lists share this shape - see
// backend/app/db.py's lists_table `kind` comment.
export interface ListEntry {
  id: number
  name: string
  kind: 'custom' | 'shopping'
  position: number
  has_share_link: boolean
}

// The bare item shape served by the public, no-login list endpoints -
// deliberately minimal, no owner/priority/category/due-date.
export interface PublicListItem {
  id: number
  text: string
  done: boolean
}

export interface PublicListResponse {
  list_name: string
  items: PublicListItem[]
}

export type NotificationKind = 'item_checked' | 'subtask_assigned' | 'access_revoked'

export interface NotificationEntry {
  id: number
  kind: NotificationKind
  message: string
  actor_username: string | null
  task_id: number | null
  created_at: string
  read: boolean
}

export interface NotificationsResponse {
  notifications: NotificationEntry[]
  unread_count: number
}
