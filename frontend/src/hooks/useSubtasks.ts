import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { subtasksApi } from '../api/subtasks'
import { TASKS_KEY } from './useTasks'
import { pushUndoSnapshot } from './undoRedoStack'
import type { TasksResponse } from '../types'

async function beginOptimisticUpdate(queryClient: ReturnType<typeof useQueryClient>) {
  await queryClient.cancelQueries({ queryKey: TASKS_KEY })
  const previous = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
  if (previous) pushUndoSnapshot(previous)
  return previous
}

function rollback(queryClient: ReturnType<typeof useQueryClient>, previous: TasksResponse | undefined) {
  if (previous) queryClient.setQueryData(TASKS_KEY, previous)
}

export function useAddSubtask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, text }: { taskId: number; text: string }) => subtasksApi.create(taskId, text),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      const tempId = -Date.now()
      const clientKey = `temp-subtask-${tempId}`
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old
          ? {
              tasks: old.tasks.map((t) =>
                t.id === vars.taskId
                  ? {
                      ...t,
                      done: false,
                      subtasks: [
                        ...t.subtasks,
                        {
                          id: tempId,
                          task_id: vars.taskId,
                          text: vars.text,
                          done: false,
                          created_at: new Date().toISOString(),
                          clientKey,
                        },
                      ],
                    }
                  : t
              ),
              can_undo: true,
              can_redo: false,
            }
          : old
      )
      toast('➕ Subtask added')
      return { previous, tempId, clientKey }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to add subtask')
    },
    onSuccess: (res, vars, ctx) => {
      // Swap the temp placeholder for the server's real subtask record,
      // keeping the same clientKey so the React key stays stable (see the
      // matching comment in useAddTask for why that matters).
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old
          ? {
              ...old,
              tasks: old.tasks.map((t) =>
                t.id === vars.taskId
                  ? {
                      ...t,
                      subtasks: t.subtasks.map((s) =>
                        s.id === ctx?.tempId && res.subtask ? { ...res.subtask, clientKey: ctx.clientKey } : s
                      ),
                    }
                  : t
              ),
            }
          : old
      )
    },
  })
}

export function useToggleSubtask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ subtaskId, done }: { subtaskId: number; done: boolean }) =>
      subtasksApi.setDone(subtaskId, done),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old
          ? {
              tasks: old.tasks.map((t) => {
                if (!t.subtasks.some((s) => s.id === vars.subtaskId)) return t
                const subtasks = t.subtasks.map((s) => (s.id === vars.subtaskId ? { ...s, done: vars.done } : s))
                // Mirrors the backend's set_subtask_done cascade exactly: an
                // uncheck always uncompletes the parent; a check only
                // completes it once every subtask is done; otherwise the
                // parent's done state is untouched.
                let done = t.done
                if (!vars.done) done = false
                else if (subtasks.every((s) => s.done)) done = true
                return { ...t, subtasks, done }
              }),
              can_undo: true,
              can_redo: false,
            }
          : old
      )
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update subtask')
    },
  })
}

export function useDeleteSubtask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (subtaskId: number) => subtasksApi.remove(subtaskId),
    onMutate: async (subtaskId) => {
      const previous = await beginOptimisticUpdate(queryClient)
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old
          ? {
              tasks: old.tasks.map((t) => {
                if (!t.subtasks.some((s) => s.id === subtaskId)) return t
                const subtasks = t.subtasks.filter((s) => s.id !== subtaskId)
                // Mirrors the backend's delete_subtask: only ever promotes to
                // done once every remaining subtask is done, never demotes.
                const done = subtasks.length > 0 && subtasks.every((s) => s.done) ? true : t.done
                return { ...t, subtasks, done }
              }),
              can_undo: true,
              can_redo: false,
            }
          : old
      )
      toast('🗑️ Subtask deleted')
      return { previous }
    },
    onError: (_err, _id, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to delete subtask')
    },
  })
}
