import { api } from './client'
import type { StatsResponse } from '../types'

export const statsApi = {
  get: () => api.get<StatsResponse>('/stats'),
}
