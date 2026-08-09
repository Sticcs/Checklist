import { api } from './client'
import type { TasksResponse } from '../types'

export const undoApi = {
  undo: () => api.post<TasksResponse>('/undo'),
  redo: () => api.post<TasksResponse>('/redo'),
}
