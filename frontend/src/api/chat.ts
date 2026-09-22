import { api } from './client'
import type { ChatMessage, ChatMessagesResponse } from '../types'

export const chatApi = {
  list: (taskId: number) => api.get<ChatMessagesResponse>(`/tasks/${taskId}/messages`),
  send: (taskId: number, text: string) => api.post<ChatMessage>(`/tasks/${taskId}/messages`, { text }),
  markRead: (taskId: number) => api.post<void>(`/tasks/${taskId}/messages/read`),
}
