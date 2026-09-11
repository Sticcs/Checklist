import { api } from './client'
import type { NotificationsResponse } from '../types'

export const notificationsApi = {
  list: () => api.get<NotificationsResponse>('/notifications'),
  markRead: (id: number) => api.post<void>(`/notifications/${id}/read`),
  markAllRead: () => api.post<void>('/notifications/read-all'),
}
