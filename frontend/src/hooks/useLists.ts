import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { listsApi } from '../api/lists'
import { TASKS_KEY } from './useTasks'
import { pushUndoSnapshot } from './undoRedoStack'
import type { ListEntry, TasksResponse } from '../types'

export const LISTS_KEY = ['lists']

function setListsData(queryClient: QueryClient, updater: (old: ListEntry[]) => ListEntry[]) {
  queryClient.setQueryData<{ lists: ListEntry[] }>(LISTS_KEY, (old) =>
    old ? { lists: updater(old.lists) } : old
  )
}

export function useLists() {
  return useQuery({ queryKey: LISTS_KEY, queryFn: listsApi.list })
}

export function useCreateList() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ kind = 'custom', expiresAt = null }: { kind?: ListEntry['kind']; expiresAt?: string | null }) =>
      listsApi.create(kind, expiresAt),
    onSuccess: (list) => {
      // A direct cache write, not invalidateQueries - the caller (see
      // TaskListPage's handleCreateList) switches the active tab to this
      // new list's id in the same breath, and a background refetch landing
      // a beat later than that tab switch let the "orphaned tab" fallback
      // effect see a `lists` array that didn't have the new list yet,
      // immediately bouncing the tab back to Assessments.
      setListsData(queryClient, (old) => [...old, list])
    },
    onError: () => toast.error('Failed to create list'),
  })
}

export function useSetListExpiresAt() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, expiresAt }: { id: number; expiresAt: string }) => listsApi.setExpiresAt(id, expiresAt),
    onSuccess: (list) => {
      setListsData(queryClient, (old) => old.map((l) => (l.id === list.id ? list : l)))
    },
    onError: () => toast.error('Failed to update expiry time'),
  })
}

// Fired automatically the moment an expiry checklist's countdown hits zero
// (see ExpiryTimer), not from a button of its own - mirrors the backend's
// clear_completed_in_list, scoped to one list rather than the account-wide
// "Clear completed" in the sidebar (useClearCompleted in useTasks.ts).
export function useClearCompletedInList() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (listId: number) => listsApi.clearCompleted(listId),
    onMutate: async (listId) => {
      const previous = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
      if (previous) pushUndoSnapshot(previous)
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old ? { ...old, tasks: old.tasks.filter((t) => !(t.list_id === listId && t.done)) } : old
      )
      return { previous }
    },
    onError: (_err, _listId, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(TASKS_KEY, ctx.previous)
    },
    onSuccess: (res) => {
      if (res.deleted_count > 0) {
        toast(`🧹 Cleared ${res.deleted_count} completed task${res.deleted_count === 1 ? '' : 's'}`)
      }
    },
  })
}

// The "Continue" flow (see ContinueExpiryButton): sets a fresh deadline,
// restarts the countdown's own clock, and flags whatever's still
// incomplete in the list (carried over from the expired cycle) so TaskCard
// can give it a light red background - mirrors the backend's
// continue_expiry_list exactly.
export function useContinueExpiryList() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, expiresAt }: { id: number; expiresAt: string }) => listsApi.continueList(id, expiresAt),
    onMutate: async ({ id, expiresAt }) => {
      const previousLists = queryClient.getQueryData<{ lists: ListEntry[] }>(LISTS_KEY)
      const previousTasks = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
      if (previousTasks) pushUndoSnapshot(previousTasks)
      setListsData(queryClient, (old) =>
        old.map((l) => (l.id === id ? { ...l, expires_at: expiresAt, cycle_started_at: new Date().toISOString() } : l))
      )
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old
          ? { ...old, tasks: old.tasks.map((t) => (t.list_id === id && !t.done ? { ...t, carried_over: true } : t)) }
          : old
      )
      return { previousLists, previousTasks }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previousLists) queryClient.setQueryData(LISTS_KEY, ctx.previousLists)
      if (ctx?.previousTasks) queryClient.setQueryData(TASKS_KEY, ctx.previousTasks)
      toast.error('Failed to continue checklist')
    },
    onSuccess: (list) => {
      // Reconciles cycle_started_at with the server's own clock - our
      // optimistic guess above used the browser's, which can drift
      // slightly.
      setListsData(queryClient, (old) => old.map((l) => (l.id === list.id ? list : l)))
      toast('🔁 Checklist continued')
    },
  })
}

export function useRenameList() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => listsApi.rename(id, name),
    onSuccess: (list) => {
      setListsData(queryClient, (old) => old.map((l) => (l.id === list.id ? list : l)))
    },
    onError: () => toast.error('Failed to rename list'),
  })
}

export function useSetListSimple() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, isSimple }: { id: number; isSimple: boolean }) => listsApi.setSimple(id, isSimple),
    onSuccess: (list) => {
      setListsData(queryClient, (old) => old.map((l) => (l.id === list.id ? list : l)))
    },
    onError: () => toast.error('Failed to change list type'),
  })
}

export function useDeleteList() {
  const queryClient = useQueryClient()
  return useMutation({
    // The backend branches on `kind` too (see delete_or_clear_list): a
    // custom or expiry list's row is deleted outright, but Shopping's (and
    // Main's) row survives with only its items cleared. The DELETE
    // response carries no body to tell the two apart, so the caller
    // (ListPanel, which already knows which list it's acting on) passes
    // `kind` through.
    mutationFn: ({ id }: { id: number; kind: ListEntry['kind'] }) => listsApi.remove(id),
    onSuccess: (_res, { id, kind }) => {
      if (kind === 'custom' || kind === 'expiry') {
        setListsData(queryClient, (old) => old.filter((l) => l.id !== id))
      }
      // Custom-list items and (Shopping's) cleared items both live in the
      // normal tasks cache too - that one still needs a refetch, since
      // there's no cheap way to know from here which task ids just
      // disappeared.
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: () => toast.error('Failed to delete list'),
  })
}

export function useCreateListShareLink() {
  return useMutation({
    mutationFn: (id: number) => listsApi.createShareLink(id),
    onError: () => toast.error('Failed to create share link'),
  })
}

export function useRegenerateListShareLink() {
  return useMutation({
    mutationFn: (id: number) => listsApi.regenerateShareLink(id),
    onError: () => toast.error('Failed to regenerate share link'),
  })
}

export function useRevokeListShareLink() {
  return useMutation({
    mutationFn: (id: number) => listsApi.revokeShareLink(id),
    onError: () => toast.error('Failed to revoke share link'),
  })
}
