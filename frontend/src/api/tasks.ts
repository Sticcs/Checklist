import { api } from './client'
import type { MarkAllCompletedResponse, ClearResponse, Task, TasksResponse } from '../types'

export const tasksApi = {
  list: () => api.get<TasksResponse>('/tasks'),
  create: (text: string, priority: string, category: string, due_date: string | null = null) =>
    api.post<Task>('/tasks', { text, priority, category, due_date }),
  update: (id: number, text: string, priority: string, category: string, due_date: string | null) =>
    api.patch<Task>(`/tasks/${id}`, { text, priority, category, due_date }),
  setDone: (id: number, done: boolean) => api.patch<Task>(`/tasks/${id}/done`, { done }),
  setPinned: (id: number, pinned: boolean) => api.patch<Task>(`/tasks/${id}/pin`, { pinned }),
  setPosition: (id: number, position: number) => api.patch<Task>(`/tasks/${id}/position`, { position }),
  setNotes: (id: number, notes: string) => api.patch<Task>(`/tasks/${id}/notes`, { notes }),
  setUrgent: (id: number, urgent: boolean) => api.patch<Task>(`/tasks/${id}/urgent`, { urgent }),
  setDueDate: (id: number, due_date: string | null) => api.patch<Task>(`/tasks/${id}/due-date`, { due_date }),
  assign: (id: number, assigned_task_id: number | null) =>
    api.patch<Task>(`/tasks/${id}/assign`, { assigned_task_id }),
  remove: (id: number) => api.delete<void>(`/tasks/${id}`),
  markAllCompleted: () => api.post<MarkAllCompletedResponse>('/tasks/mark-all-completed'),
  clearCompleted: () => api.post<ClearResponse>('/tasks/clear-completed'),
  clearAll: () => api.post<ClearResponse>('/tasks/clear-all'),
}
