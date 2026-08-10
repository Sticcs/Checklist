import { api } from './client'
import type { ExportPayload, ImportResponse } from '../types'

export const dataApi = {
  // Export itself is a plain <a href="/api/export" download> link (see
  // Sidebar) rather than a fetch call - it's a file download with a
  // server-set filename (Content-Disposition), which the browser already
  // handles natively over the same cookie-authenticated session.
  importData: (payload: ExportPayload) => api.post<ImportResponse>('/import', payload),
}
