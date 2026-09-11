import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { notificationsApi } from '../api/notifications'
import type { NotificationsResponse } from '../types'

export const NOTIFICATIONS_KEY = ['notifications']

// The first app-wide poll in this app - every other poll (see
// AssignmentWorkspace's pollQuery) is scoped to one open assignment. This
// one needs to run in the background regardless of what's on screen, since
// the whole point is surfacing things the user isn't currently looking at
// (their access being revoked, being assigned a subtask, a collaborator
// checking something off elsewhere).
export function useNotifications() {
  return useQuery({
    queryKey: NOTIFICATIONS_KEY,
    queryFn: notificationsApi.list,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  })
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: NOTIFICATIONS_KEY })
      const previous = queryClient.getQueryData<NotificationsResponse>(NOTIFICATIONS_KEY)
      queryClient.setQueryData<NotificationsResponse>(NOTIFICATIONS_KEY, (old) =>
        old
          ? {
              notifications: old.notifications.map((n) => (n.id === id ? { ...n, read: true } : n)),
              unread_count: Math.max(0, old.unread_count - (old.notifications.find((n) => n.id === id && !n.read) ? 1 : 0)),
            }
          : old
      )
      return { previous }
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(NOTIFICATIONS_KEY, ctx.previous)
    },
  })
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: NOTIFICATIONS_KEY })
      const previous = queryClient.getQueryData<NotificationsResponse>(NOTIFICATIONS_KEY)
      queryClient.setQueryData<NotificationsResponse>(NOTIFICATIONS_KEY, (old) =>
        old ? { notifications: old.notifications.map((n) => ({ ...n, read: true })), unread_count: 0 } : old
      )
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(NOTIFICATIONS_KEY, ctx.previous)
    },
  })
}
