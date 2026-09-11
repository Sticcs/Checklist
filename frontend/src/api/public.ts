import { api } from './client'
import type { PublicListResponse } from '../types'

// No auth of any kind - the token itself is the credential. Reuses the same
// `api` client as everywhere else (it always sends `credentials: 'include'`,
// but that's harmless here: these routes never check for a cookie, and a
// visitor with no session at all simply has none to send).
export const publicApi = {
  getList: (token: string) => api.get<PublicListResponse>(`/public/lists/${token}`),
  setItemDone: (token: string, itemId: number, done: boolean) =>
    api.patch<PublicListResponse>(`/public/lists/${token}/items/${itemId}`, { done }),
}
