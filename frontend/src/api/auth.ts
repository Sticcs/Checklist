import { api } from './client'
import type { ImportResponse, User, WebsiteLinkStatus } from '../types'

export const authApi = {
  me: () => api.get<User>('/auth/me'),
  signup: (username: string, password: string) =>
    api.post<{ username: string }>('/auth/signup', { username, password }),
  login: (username: string, password: string) => api.post<User>('/auth/login', { username, password }),
  guest: () => api.post<User>('/auth/guest'),
  logout: () => api.post<void>('/auth/logout'),
  // Desktop app only (see useIsDesktopApp). Pulls the given website
  // account's data into whichever local account is currently logged in, or
  // (if `creds` is omitted) reuses whatever website account this local
  // account is already linked to - see routers/auth.py's
  // _resolve_website_credentials and websiteLink.ts.
  sync: (creds?: { username: string; password: string }) => api.post<ImportResponse>('/auth/sync', creds ?? {}),
  // The opposite direction - pushes the currently logged-in local
  // account's data up into the given (or already-linked) website account.
  push: (creds?: { username: string; password: string }) => api.post<ImportResponse>('/auth/push', creds ?? {}),
  websiteLinkStatus: () => api.get<WebsiteLinkStatus>('/auth/website-link'),
  unlinkWebsite: () => api.post<void>('/auth/website-link/clear'),
}
