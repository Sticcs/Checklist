import { useSyncExternalStore } from 'react'

// Tracks whether local task data has changed since the last successful Push
// to the website (see WebsiteSyncButtons/usePushToWebsite) - drives the
// desktop app's autosave timer (AutosaveIndicator.tsx) and its close-window
// save prompt (ExitSavePrompt.tsx). Plain module store (same pattern as
// undoRedoStack.ts) rather than React state, since it needs to be set from
// inside mutation callbacks that aren't components. Lives in memory only,
// reset on logout (see AuthContext) same as the undo/redo stacks.
let dirty = false
const listeners = new Set<() => void>()

function notify(): void {
  for (const l of listeners) l()
}

export function markDirty(): void {
  if (dirty) return
  dirty = true
  notify()
}

export function markSaved(): void {
  if (!dirty) return
  dirty = false
  notify()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): boolean {
  return dirty
}

export function isDirty(): boolean {
  return dirty
}

export function useIsDirty(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot)
}
