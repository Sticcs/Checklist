import { api } from './client'
import type { ClearResponse, ListEntry, ShareLink } from '../types'

export const listsApi = {
  list: () => api.get<{ lists: ListEntry[] }>('/lists'),
  create: (kind: ListEntry['kind'] = 'custom', expiresAt: string | null = null) =>
    api.post<ListEntry>('/lists', { kind, expires_at: expiresAt }),
  setExpiresAt: (id: number, expiresAt: string) =>
    api.patch<ListEntry>(`/lists/${id}/expires-at`, { expires_at: expiresAt }),
  clearCompleted: (id: number) => api.post<ClearResponse>(`/lists/${id}/clear-completed`),
  continueList: (id: number, expiresAt: string) =>
    api.post<ListEntry>(`/lists/${id}/continue`, { expires_at: expiresAt }),
  rename: (id: number, name: string) => api.patch<ListEntry>(`/lists/${id}`, { name }),
  setSimple: (id: number, isSimple: boolean) =>
    api.patch<ListEntry>(`/lists/${id}/simple`, { is_simple: isSimple }),
  remove: (id: number) => api.delete<void>(`/lists/${id}`),
  createShareLink: (id: number) => api.post<ShareLink>(`/lists/${id}/share-link`),
  regenerateShareLink: (id: number) => api.post<ShareLink>(`/lists/${id}/share-link/regenerate`),
  revokeShareLink: (id: number) => api.delete<void>(`/lists/${id}/share-link`),
}
