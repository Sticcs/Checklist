import { api } from './client'
import type { SubtaskClearCompletedResponse, SubtaskMutationResponse } from '../types'

export const subtasksApi = {
  create: (taskId: number, text: string, linkedSubtaskId: number | null = null) =>
    api.post<SubtaskMutationResponse>(`/tasks/${taskId}/subtasks`, {
      text,
      linked_subtask_id: linkedSubtaskId,
    }),
  clearCompleted: (taskId: number) =>
    api.post<SubtaskClearCompletedResponse>(`/tasks/${taskId}/subtasks/clear-completed`),
  setDone: (subtaskId: number, done: boolean) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}`, { done }),
  setText: (subtaskId: number, text: string) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}/text`, { text }),
  setUrgent: (subtaskId: number, urgent: boolean) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}/urgent`, { urgent }),
  setDueDate: (subtaskId: number, due_date: string | null) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}/due-date`, { due_date }),
  setNotes: (subtaskId: number, notes: string) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}/notes`, { notes }),
  setAssignee: (subtaskId: number, assigned_username: string | null) =>
    api.patch<SubtaskMutationResponse>(`/subtasks/${subtaskId}/assignee`, { assigned_username }),
  remove: (subtaskId: number) => api.delete<SubtaskMutationResponse>(`/subtasks/${subtaskId}`),
}
