import { useSyncExternalStore } from 'react'

// Remembers the website credentials used for the most recent successful
// Pull or Push (see WebsiteSyncButtons), in memory only for the lifetime of
// this run of the app - never written to disk, matching the existing "never
// stored" guarantee in routers/auth.py. Once linked, the autosave timer and
// Ctrl+S (AutosaveIndicator.tsx) and the exit-save prompt (ExitSavePrompt.tsx)
// can push without asking again. Reset on logout (see AuthContext).
export interface WebsiteCredentials {
  username: string
  password: string
}

let linked: WebsiteCredentials | null = null
const listeners = new Set<() => void>()

function notify(): void {
  for (const l of listeners) l()
}

export function setLinkedCredentials(username: string, password: string): void {
  linked = { username, password }
  notify()
}

export function clearLinkedCredentials(): void {
  if (!linked) return
  linked = null
  notify()
}

export function getLinkedCredentials(): WebsiteCredentials | null {
  return linked
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useLinkedCredentials(): WebsiteCredentials | null {
  return useSyncExternalStore(subscribe, getLinkedCredentials)
}
