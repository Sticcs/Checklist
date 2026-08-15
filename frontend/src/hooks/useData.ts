import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { dataApi } from '../api/data'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { TASKS_KEY } from './useTasks'
import { markDirty, markSaved } from './saveState'
import { setLinked, clearLinked } from './websiteLink'
import { useIsDesktopApp } from './useIsDesktopApp'
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

// Restores the client-side "linked" indicator (websiteLink.ts) from what
// the backend already has stored (crud.get_website_link) - runs once on
// startup so a relaunched desktop app shows itself linked (and the autosave
// timer/Ctrl+S/exit-save prompt turn back on) without the user re-entering
// website credentials, per the whole point of this being persisted server-
// side now instead of only living in memory for one run of the app.
export function useWebsiteLinkStatus() {
  const isDesktopApp = useIsDesktopApp()
  return useQuery({
    queryKey: ['website-link'],
    queryFn: async () => {
      const status = await authApi.websiteLinkStatus()
      if (status.linked && status.username) setLinked(status.username)
      else clearLinked()
      return status
    },
    enabled: isDesktopApp,
    staleTime: Infinity,
  })
}

export function useSyncFromWebsite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (creds?: { username: string; password: string }) => authApi.sync(creds),
    onSuccess: (res: ImportResponse, creds) => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      if (creds) setLinked(creds.username)
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
    mutationFn: (creds?: { username: string; password: string }) => authApi.push(creds),
    onSuccess: (res: ImportResponse, creds) => {
      if (creds) setLinked(creds.username)
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

export function useUnlinkWebsite() {
  return useMutation({
    mutationFn: () => authApi.unlinkWebsite(),
    onSuccess: () => {
      clearLinked()
      toast('🔌 Unlinked from website account')
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Couldn't unlink - try again")
    },
  })
}
