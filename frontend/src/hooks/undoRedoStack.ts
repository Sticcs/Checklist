import type { TasksResponse } from '../types'

// A client-side mirror of the backend's per-user undo/redo stack
// (backend/app/undo.py): every optimistic mutation pushes the snapshot it's
// about to overwrite, so pressing Undo/Redo can apply the previous/next
// state immediately instead of waiting on a round trip. It's a *mirror*, not
// a replacement - the actual POST /api/undo|redo still fires and its
// response is written into the cache to keep this in sync with the
// server's authoritative history. Lives in memory only (module scope, reset
// on reload or logout), same lost-on-restart behavior as the backend's own
// stack - not a new limitation.
const MAX_STACK_SIZE = 20

let undoStack: TasksResponse[] = []
let redoStack: TasksResponse[] = []

export function pushUndoSnapshot(snapshot: TasksResponse): void {
  undoStack.push(snapshot)
  redoStack = []
  if (undoStack.length > MAX_STACK_SIZE) undoStack.shift()
}

export function popUndo(current: TasksResponse): TasksResponse | undefined {
  const prev = undoStack.pop()
  if (prev) redoStack.push(current)
  return prev
}

export function popRedo(current: TasksResponse): TasksResponse | undefined {
  const next = redoStack.pop()
  if (next) undoStack.push(current)
  return next
}

export function undoStackHasMore(): boolean {
  return undoStack.length > 0
}

export function redoStackHasMore(): boolean {
  return redoStack.length > 0
}

export function resetUndoRedoStacks(): void {
  undoStack = []
  redoStack = []
}
