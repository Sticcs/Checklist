import { api } from './client'
import type { ImportResponse, User } from '../types'

export const authApi = {
  me: () => api.get<User>('/auth/me'),
  signup: (username: string, password: string) =>
    api.post<{ username: string }>('/auth/signup', { username, password }),
  login: (username: string, password: string) => api.post<User>('/auth/login', { username, password }),
  guest: () => api.post<User>('/auth/guest'),
  logout: () => api.post<void>('/auth/logout'),
  // Desktop app only (see useIsDesktopApp) - pulls the given website
  // account's data into whichever local account is currently logged in.
  sync: (username: string, password: string) =>
    api.post<ImportResponse>('/auth/sync', { username, password }),
}
