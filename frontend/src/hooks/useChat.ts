import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { chatApi } from '../api/chat'

export const CHAT_KEY = (taskId: number) => ['assignment-chat', taskId]

// Always enabled (not gated on the chat panel being open) so the round
// button's unread badge stays current even while the panel is closed -
// `open` just controls how often it refetches: close to real-time (~4s)
// while you're actually looking at it, the same ~20s cadence as the rest
// of the workspace's polling otherwise.
export function useChatMessages(taskId: number, open: boolean) {
  return useQuery({
    queryKey: CHAT_KEY(taskId),
    queryFn: () => chatApi.list(taskId),
    refetchInterval: open ? 4_000 : 20_000,
    refetchIntervalInBackground: false,
  })
}

export function useSendChatMessage(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (text: string) => chatApi.send(taskId, text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHAT_KEY(taskId) })
    },
    onError: () => toast.error('Failed to send message'),
  })
}

export function useMarkChatRead(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => chatApi.markRead(taskId),
    // Refetches (not just an optimistic zero-out) so the panel reflects
    // the truly-latest read state - mirrors useRemoveCollaborator's
    // invalidateQueries pattern.
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHAT_KEY(taskId) })
    },
  })
}
