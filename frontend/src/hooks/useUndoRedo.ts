import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { undoApi } from '../api/undo'
import { TASKS_KEY } from './useTasks'

// /api/undo and /api/redo already return the fresh, server-authoritative task
// list in their response - write it straight into the cache instead of
// invalidating and firing a redundant refetch. This isn't an optimistic
// update (nothing is guessed ahead of the server); it's just skipping a
// round trip for data the response already contains.
export function useUndo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => undoApi.undo(),
    onSuccess: (data) => {
      queryClient.setQueryData(TASKS_KEY, data)
      toast('↩️ Undid last action')
    },
  })
}

export function useRedo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => undoApi.redo(),
    onSuccess: (data) => {
      queryClient.setQueryData(TASKS_KEY, data)
      toast('↪️ Redid last action')
    },
  })
}
