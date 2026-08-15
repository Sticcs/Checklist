import { useSyncExternalStore } from 'react'

// Visibility of the "save before you exit?" modal (ExitSavePrompt.tsx) -
// shown when backend/desktop.py's window.events.closing handler intercepts
// the window being closed with unsaved changes still pending (see
// saveState.ts/websiteLink.ts) and calls back into
// window.__checklistShowExitPrompt (wired up by ExitSavePrompt itself).
// Plain module store, same pattern as saveState.ts/websiteLink.ts.
let visible = false
const listeners = new Set<() => void>()

function notify(): void {
  for (const l of listeners) l()
}

export function showExitPrompt(): void {
  if (visible) return
  visible = true
  notify()
}

export function hideExitPrompt(): void {
  if (!visible) return
  visible = false
  notify()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): boolean {
  return visible
}

export function useExitPromptVisible(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot)
}
