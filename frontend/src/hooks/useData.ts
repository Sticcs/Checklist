import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { dataApi } from '../api/data'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { TASKS_KEY } from './useTasks'
import { markDirty, markSaved } from './saveState'
import type { ExportPayload, ImportResponse } from '../types'

export function useImportData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ExportPayload) => dataApi.importData(payload),
    onSuccess: (res: ImportResponse) => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      // A file import is additive (merges into whatever's already there),
      // so it diverges from the website even if nothing's been pushed since
      // - the desktop app's autosave (see saveState.ts) needs to catch that.
      markDirty()
      toast(
        `📥 Imported ${res.imported_tasks} task${res.imported_tasks === 1 ? '' : 's'}` +
          (res.imported_subtasks > 0 ? ` (${res.imported_subtasks} subtasks)` : '')
      )
    },
    onError: () => {
      toast.error("Couldn't import - make sure the file is a Checklist export")
    },
  })
}

export function useSyncFromWebsite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      authApi.sync(username, password),
    onSuccess: (res: ImportResponse) => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      // Pull replaces the local account with exactly what the website has
      // (see crud.import_data's replace mode), so right after this they're
      // identical - nothing new to push yet.
      markSaved()
      toast(
        `🔄 Synced ${res.imported_tasks} task${res.imported_tasks === 1 ? '' : 's'}` +
          (res.imported_subtasks > 0 ? ` (${res.imported_subtasks} subtasks)` : '')
      )
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Couldn't sync - try again")
    },
  })
}

export function usePushToWebsite() {
  // No TASKS_KEY invalidation - push only changes the *website's* data, the
  // local account this ran from is untouched (see the backend test asserting
  // exactly that).
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      authApi.push(username, password),
    onSuccess: (res: ImportResponse) => {
      markSaved()
      toast(
        `⬆️ Pushed ${res.imported_tasks} task${res.imported_tasks === 1 ? '' : 's'} to the website` +
          (res.imported_subtasks > 0 ? ` (${res.imported_subtasks} subtasks)` : '')
      )
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Couldn't push - try again")
    },
  })
}
