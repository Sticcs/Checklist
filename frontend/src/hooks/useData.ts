import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { dataApi } from '../api/data'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { TASKS_KEY } from './useTasks'
import type { ExportPayload, ImportResponse } from '../types'

export function useImportData() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ExportPayload) => dataApi.importData(payload),
    onSuccess: (res: ImportResponse) => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
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
