import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { undoApi } from '../api/undo'
import { TASKS_KEY } from './useTasks'
import { STATS_KEY } from './useStats'
import { popRedo, popUndo, redoStackHasMore, undoStackHasMore } from './undoRedoStack'
import { markDirty } from './saveState'
import type { TasksResponse } from '../types'

// Optimistic when the client-side mirror stack (undoRedoStack.ts) has a
// snapshot to pop - applies it immediately instead of waiting on the round
// trip. Falls back to a plain wait-for-response when it doesn't (e.g. right
// after a page load, before any mutation has fed the mirror stack, even
// though the server's own history from an earlier session is still there).
//
// When applied optimistically, onSuccess reconciles ONLY the can_undo/
// can_redo flags from the server response - never the tasks array itself.
// Rewriting the whole array there was tried first, and it caused its own
// flicker: two full-array cache writes landing a beat apart made
// AnimatePresence treat the item as removed-and-re-added (replaying its
// exit/enter animation) even though its key never changed - same family of
// bug as the temp-id flicker fixed in useAddTask, different trigger. A
// flag-only patch keeps the `tasks` array reference untouched, so nothing
// downstream re-renders at all.
export function useUndo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => undoApi.undo(),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: TASKS_KEY })
      const current = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
      if (!current) return { applied: false }
      const prev = popUndo(current)
      if (!prev) return { applied: false, current }
      queryClient.setQueryData(TASKS_KEY, {
        ...prev,
        can_undo: undoStackHasMore(),
        can_redo: true, // guaranteed: popUndo just pushed `current` onto the redo stack
      })
      toast('↩️ Undid last action')
      return { applied: true, current }
    },
    onSuccess: (data, _vars, ctx) => {
      // The server may have just adjusted the completion log (undoing a
      // completion drops it from the streak, redoing one re-adds it - see
      // crud.adjust_completion_log) - the stats panel has no way to guess
      // that optimistically, so it refetches here regardless of whether the
      // tasks array itself was applied optimistically or not.
      queryClient.invalidateQueries({ queryKey: STATS_KEY })
      if (ctx?.applied) {
        queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
          old ? { ...old, can_undo: data.can_undo, can_redo: data.can_redo } : old
        )
        return
      }
      queryClient.setQueryData(TASKS_KEY, data)
      markDirty()
      toast('↩️ Undid last action')
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.applied && ctx.current) queryClient.setQueryData(TASKS_KEY, ctx.current)
      toast.error('Nothing to undo')
    },
  })
}

export function useRedo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => undoApi.redo(),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: TASKS_KEY })
      const current = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
      if (!current) return { applied: false }
      const next = popRedo(current)
      if (!next) return { applied: false, current }
      queryClient.setQueryData(TASKS_KEY, {
        ...next,
        can_undo: true, // guaranteed: popRedo just pushed `current` onto the undo stack
        can_redo: redoStackHasMore(),
      })
      toast('↪️ Redid last action')
      return { applied: true, current }
    },
    onSuccess: (data, _vars, ctx) => {
      queryClient.invalidateQueries({ queryKey: STATS_KEY })
      if (ctx?.applied) {
        queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
          old ? { ...old, can_undo: data.can_undo, can_redo: data.can_redo } : old
        )
        return
      }
      queryClient.setQueryData(TASKS_KEY, data)
      markDirty()
      toast('↪️ Redid last action')
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.applied && ctx.current) queryClient.setQueryData(TASKS_KEY, ctx.current)
      toast.error('Nothing to redo')
    },
  })
}
