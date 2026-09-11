import { api } from './client'
import type { ListEntry, ShareLink } from '../types'

export const listsApi = {
  list: () => api.get<{ lists: ListEntry[] }>('/lists'),
  create: () => api.post<ListEntry>('/lists'),
  rename: (id: number, name: string) => api.patch<ListEntry>(`/lists/${id}`, { name }),
  remove: (id: number) => api.delete<void>(`/lists/${id}`),
  createShareLink: (id: number) => api.post<ShareLink>(`/lists/${id}/share-link`),
  regenerateShareLink: (id: number) => api.post<ShareLink>(`/lists/${id}/share-link/regenerate`),
  revokeShareLink: (id: number) => api.delete<void>(`/lists/${id}/share-link`),
}
