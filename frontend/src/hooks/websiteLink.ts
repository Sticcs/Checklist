import { useSyncExternalStore } from 'react'

// Whether the current local account has a website account linked - the
// actual credentials are never held here (or anywhere in the frontend)
// beyond the single request that first sends them: the backend remembers
// them itself, keyed to the local account (see crud.set_website_link /
// GET|POST /api/auth/website-link), so relaunching the app stays linked
// without asking again. This is just a client-side mirror of that - reading
// its username for display, and its truthiness to gate the autosave timer/
// Ctrl+S/exit-save prompt (AutosaveIndicator.tsx, ExitSavePrompt.tsx),
// which push with no credentials and let the backend fill them in from what
// it already has stored.
let linkedUsername: string | null = null
const listeners = new Set<() => void>()

function notify(): void {
  for (const l of listeners) l()
}

export function setLinked(username: string): void {
  linkedUsername = username
  notify()
}

export function clearLinked(): void {
  if (linkedUsername === null) return
  linkedUsername = null
  notify()
}

export function getLinked(): string | null {
  return linkedUsername
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useLinked(): string | null {
  return useSyncExternalStore(subscribe, getLinked)
}
