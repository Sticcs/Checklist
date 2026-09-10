import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { collaborationApi } from '../api/collaboration'
import { SHARED_KEY } from './useTasks'
import type { Task } from '../types'

export function useSharedWithMe() {
  return useQuery({ queryKey: SHARED_KEY, queryFn: collaborationApi.sharedWithMe })
}

export function useCreateShareLink() {
  return useMutation({
    mutationFn: (taskId: number) => collaborationApi.createShareLink(taskId),
    onError: () => toast.error('Failed to create share link'),
  })
}

export function useRegenerateShareLink() {
  return useMutation({
    mutationFn: (taskId: number) => collaborationApi.regenerateShareLink(taskId),
    onError: () => toast.error('Failed to regenerate share link'),
  })
}

export function useRevokeShareLink() {
  return useMutation({
    mutationFn: (taskId: number) => collaborationApi.revokeShareLink(taskId),
    onError: () => toast.error('Failed to revoke share link'),
  })
}

export function useCollaborators(taskId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['collaborators', taskId],
    queryFn: () => collaborationApi.getCollaborators(taskId),
    enabled,
  })
}

export function useRemoveCollaborator() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, username }: { taskId: number; username: string }) =>
      collaborationApi.removeCollaborator(taskId, username),
    onSuccess: (_res, vars) => {
      queryClient.invalidateQueries({ queryKey: ['collaborators', vars.taskId] })
    },
    onError: () => toast.error('Failed to remove collaborator'),
  })
}

// Called once, right after login/signup/guest-continue, if a share link's
// token was captured pre-auth (see main.tsx's sessionStorage bootstrap).
// Seeds the joined task straight into SHARED_KEY so the workspace can open
// immediately without waiting on a separate shared-with-me refetch.
export function useJoinAssignment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (token: string) => collaborationApi.join(token),
    onSuccess: (task) => {
      queryClient.setQueryData<Task[]>(SHARED_KEY, (old) => {
        if (!old) return old
        return old.some((t) => t.id === task.id) ? old.map((t) => (t.id === task.id ? task : t)) : [task, ...old]
      })
    },
    onError: () => toast.error("This share link is invalid or has been revoked"),
  })
}
