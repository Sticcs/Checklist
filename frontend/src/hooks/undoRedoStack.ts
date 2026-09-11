import type { TasksResponse } from '../types'
import { markDirty } from './saveState'

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

// Every structural mutation (add/edit/delete/reorder/etc, plus Undo/Redo
// itself) goes through pushUndoSnapshot/popUndo/popRedo, which makes this
// the one choke point to also flag "local data has changed since the last
// Push" for the desktop app's autosave (see saveState.ts). Notes autosave is
// the one exception - it deliberately skips this stack (see useSetTaskNotes)
// and marks itself dirty directly.
export function pushUndoSnapshot(snapshot: TasksResponse): void {
  undoStack.push(snapshot)
  redoStack = []
  if (undoStack.length > MAX_STACK_SIZE) undoStack.shift()
  markDirty()
}

export function popUndo(current: TasksResponse): TasksResponse | undefined {
  const prev = undoStack.pop()
  if (prev) {
    redoStack.push(current)
    markDirty()
  }
  return prev
}

export function popRedo(current: TasksResponse): TasksResponse | undefined {
  const next = redoStack.pop()
  if (next) {
    undoStack.push(current)
    markDirty()
  }
  return next
}

// Called when a just-pushed snapshot turns out to have no real counterpart
// on the server (e.g. deleting a task that was already gone - the route
// 404s before crud.delete_task/undo.save_snapshot ever runs) - removes it
// so the mirror doesn't end up permanently one entry ahead of the server's
// real stack. Deliberately distinct from popUndo: this discards the push
// outright rather than "undoing" it (which would move it onto the redo
// stack, implying there's something real to redo back to).
export function discardLastPushedSnapshot(): void {
  undoStack.pop()
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
