import { api } from './client'
import type { User } from '../types'

export const authApi = {
  me: () => api.get<User>('/auth/me'),
  signup: (username: string, password: string) =>
    api.post<{ username: string }>('/auth/signup', { username, password }),
  login: (username: string, password: string) => api.post<User>('/auth/login', { username, password }),
  guest: () => api.post<User>('/auth/guest'),
  logout: () => api.post<void>('/auth/logout'),
}
