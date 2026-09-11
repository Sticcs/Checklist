import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { listsApi } from '../api/lists'
import type { ListEntry } from '../types'

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
    mutationFn: () => listsApi.create(),
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

export function useDeleteList() {
  const queryClient = useQueryClient()
  return useMutation({
    // The backend branches on `kind` too (see delete_or_clear_list): a
    // custom list's row is deleted outright, but Shopping's row survives
    // with only its items cleared. The DELETE response carries no body to
    // tell the two apart, so the caller (ListPanel, which already knows
    // which list it's acting on) passes `kind` through.
    mutationFn: ({ id }: { id: number; kind: ListEntry['kind'] }) => listsApi.remove(id),
    onSuccess: (_res, { id, kind }) => {
      if (kind === 'custom') {
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
