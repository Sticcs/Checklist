import { api } from './client'
import type { SubtaskMutationResponse } from '../types'

export const subtasksApi = {
  create: (taskId: number, text: string) =>
    api.post<SubtaskMutationResponse>(`/tasks/${taskId}/subtasks`, { text }),
  setDone: (subtaskId: number, done: boolean) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}`, { done }),
  setUrgent: (subtaskId: number, urgent: boolean) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}/urgent`, { urgent }),
  setDueDate: (subtaskId: number, due_date: string | null) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}/due-date`, { due_date }),
  setNotes: (subtaskId: number, notes: string) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}/notes`, { notes }),
  remove: (subtaskId: number) => api.delete<SubtaskMutationResponse>(`/subtasks/${subtaskId}`),
}
