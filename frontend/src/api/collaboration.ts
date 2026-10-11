import { api } from './client'
import type { Collaborator, PresenceEntry, ShareLink, Task } from '../types'

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
  // POST, not GET - it has a side effect (records a heartbeat) each call,
  // matching the backend's own reasoning (see routers/collaboration.py).
  // pageId reports which page the caller is currently on, so other viewers
  // can "follow" roughly where someone is (see AssignmentWorkspace's
  // presence-avatar click handler).
  touchPresence: (taskId: number, pageId: string | null) =>
    api.post<{ online: PresenceEntry[] }>(`/tasks/${taskId}/presence`, { page_id: pageId }),
}
