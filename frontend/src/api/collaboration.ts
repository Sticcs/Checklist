import { api } from './client'
import type { Collaborator, ShareLink, Task } from '../types'

export const collaborationApi = {
  createShareLink: (taskId: number) => api.post<ShareLink>(`/tasks/${taskId}/share-link`),
  regenerateShareLink: (taskId: number) => api.post<ShareLink>(`/tasks/${taskId}/share-link/regenerate`),
  revokeShareLink: (taskId: number) => api.delete<void>(`/tasks/${taskId}/share-link`),
  getCollaborators: (taskId: number) =>
    api.get<{ collaborators: Collaborator[] }>(`/tasks/${taskId}/collaborators`),
  removeCollaborator: (taskId: number, username: string) =>
    api.delete<void>(`/tasks/${taskId}/collaborators/${encodeURIComponent(username)}`),
  join: (token: string) => api.post<Task>(`/assignments/join/${encodeURIComponent(token)}`),
  sharedWithMe: () => api.get<Task[]>('/tasks/shared-with-me'),
  getTask: (taskId: number) => api.get<Task>(`/tasks/${taskId}`),
}
