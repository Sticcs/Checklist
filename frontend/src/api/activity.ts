import { api } from './client'
import type { ActivityEntry } from '../types'

export const activityApi = {
  list: (limit = 15) => api.get<ActivityEntry[]>(`/activity?limit=${limit}`),
}
