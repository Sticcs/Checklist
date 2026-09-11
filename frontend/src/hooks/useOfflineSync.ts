import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useOnlineStatus } from './useOnlineStatus'
import { useOutbox } from './useOutbox'
import { getOutbox, removeFromOutbox, type OutboxEntry } from '../lib/offlineOutbox'
import { tasksApi } from '../api/tasks'
import { subtasksApi } from '../api/subtasks'
import { ApiError } from '../api/client'
import { TASKS_KEY } from './useTasks'

async function send(entry: OutboxEntry) {
  if (entry.kind === 'task') {
    const { text, priority, category, dueDate, listId } = entry.payload
    await tasksApi.create(text, priority, category, dueDate, listId ?? null)
  } else {
    await subtasksApi.create(entry.payload.taskId, entry.payload.text)
  }
}

// Mounted once near the app root. Whenever the browser is online and the
// outbox (see offlineOutbox.ts) isn't empty - right after reconnecting, or
// right at startup if a previous session left something queued - this
// replays each entry in the order it was queued, using the plain API
// functions directly rather than the useAddTask/useAddSubtask mutation
// hooks: those hooks' own onError is what feeds this outbox in the first
// place, and calling them again here would re-queue a still-failing send in
// a loop instead of just leaving it for the next retry.
export function useOfflineSync() {
  const online = useOnlineStatus()
  const outbox = useOutbox()
  const queryClient = useQueryClient()
  const flushing = useRef(false)

  useEffect(() => {
    if (!online || flushing.current) return
    if (getOutbox().length === 0) return

    flushing.current = true
    ;(async () => {
      let sentAny = false
      for (const entry of getOutbox()) {
        try {
          await send(entry)
          removeFromOutbox(entry.id)
          sentAny = true
          toast.success(`Sent: "${entry.label}"`)
        } catch (err) {
          if (err instanceof ApiError) {
            // The server itself rejected it (not a connectivity problem) -
            // retrying it unchanged would just fail the same way forever.
            removeFromOutbox(entry.id)
            toast.error(`Couldn't send "${entry.label}" - ${err.message}`)
          } else {
            // Still unreachable - stop here and wait for the next 'online'
            // transition rather than hammering through the rest out of order.
            break
          }
        }
      }
      if (sentAny) queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      flushing.current = false
    })()
  }, [online, outbox, queryClient])
}
