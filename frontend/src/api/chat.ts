import { api } from './client'
import type { ChatMessage, ChatMessagesResponse, ChatSummaryResponse } from '../types'

export const chatApi = {
  list: (taskId: number) => api.get<ChatMessagesResponse>(`/tasks/${taskId}/messages`),
  send: (taskId: number, text: string) => api.post<ChatMessage>(`/tasks/${taskId}/messages`, { text }),
  markRead: (taskId: number) => api.post<void>(`/tasks/${taskId}/messages/read`),
  // Every assignment the caller can see (owned or collaborator) with its
  // own unread count - powers ChatLauncher's main-screen conversation list.
  summary: () => api.get<ChatSummaryResponse>('/chat/summary'),
}
