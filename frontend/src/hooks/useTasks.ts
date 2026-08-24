import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { tasksApi } from '../api/tasks'
import type { Task, TasksResponse } from '../types'
import { pushUndoSnapshot } from './undoRedoStack'
import { markDirty } from './saveState'
import { STATS_KEY } from './useStats'

export const TASKS_KEY = ['tasks']

// Shared by every mutation below: cancel any in-flight refetch (so it can't
// clobber our optimistic write when it resolves), snapshot the current cache
// for rollback, then hand the caller the previous data to build the
// optimistic update from. Also mirrors that same snapshot onto the client-
// side undo/redo stack (see undoRedoStack.ts) - every mutation here calls
// the backend's save_snapshot() first too, so this stays in lockstep with
// the server's own history.
async function beginOptimisticUpdate(queryClient: QueryClient) {
  await queryClient.cancelQueries({ queryKey: TASKS_KEY })
  const previous = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
  if (previous) pushUndoSnapshot(previous)
  return previous
}

function setTasksData(queryClient: QueryClient, updater: (old: TasksResponse) => TasksResponse) {
  queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) => (old ? updater(old) : old))
}

function rollback(queryClient: QueryClient, previous: TasksResponse | undefined) {
  if (previous) queryClient.setQueryData(TASKS_KEY, previous)
}

// None of these mutations refetch on settle. Each onMutate already applies
// the exact change the server will make (mirroring the backend's cascade
// logic precisely), and onSuccess (where used) reconciles any server-
// generated values a temp optimistic entry couldn't know (real id,
// created_at, etc). A trailing invalidate-refetch was tried here first, but
// its background response landing a beat after the optimistic write caused
// a visible flicker - the item briefly vanishing and reappearing, or an exit
// animation replaying - for no benefit, since there was nothing left for it
// to correct. If the cache ever needs a hard resync, a page reload does it.

export function useTasks() {
  return useQuery({ queryKey: TASKS_KEY, queryFn: tasksApi.list })
}

export function useAddTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      text,
      priority,
      category,
      dueDate,
    }: {
      text: string
      priority: string
      category: string
      dueDate: string | null
    }) => tasksApi.create(text, priority, category, dueDate),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      const tempId = -Date.now()
      const clientKey = `temp-task-${tempId}`
      const positions = previous?.tasks.map((t) => t.position) ?? []
      const optimisticTask: Task = {
        id: tempId,
        text: vars.text,
        done: false,
        priority: vars.priority,
        category: vars.category,
        due_date: vars.dueDate,
        created_at: new Date().toISOString(),
        username: '',
        pinned: false,
        position: (positions.length > 0 ? Math.min(...positions) : 0) - 1,
        notes: null,
        urgent: false,
        assigned_task_id: null,
        subtasks: [],
        clientKey,
      }
      setTasksData(queryClient, (old) => ({
        tasks: [optimisticTask, ...old.tasks],
        can_undo: true,
        can_redo: false,
      }))
      toast.success('Task added')
      return { previous, tempId, clientKey }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to add task')
    },
    onSuccess: (task, _vars, ctx) => {
      // Swap the temp negative-id placeholder for the server's real record
      // (real id, created_at, position) - keeping the same clientKey so the
      // rendered list item's React key doesn't change. If it did, React
      // would treat this as the old item unmounting and a new one mounting,
      // replaying the exit/enter animations as a visible flicker instead of
      // updating the existing element in place.
      setTasksData(queryClient, (old) => ({
        ...old,
        tasks: old.tasks.map((t) =>
          t.id === ctx?.tempId ? { ...task, subtasks: [], clientKey: ctx.clientKey } : t
        ),
      }))
    },
  })
}

export function useEditTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      text,
      priority,
      category,
      dueDate,
    }: {
      id: number
      text: string
      priority: string
      category: string
      dueDate: string | null
    }) => tasksApi.update(id, text, priority, category, dueDate),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) =>
          t.id === vars.id
            ? { ...t, text: vars.text, priority: vars.priority, category: vars.category, due_date: vars.dueDate }
            : t
        ),
        can_undo: true,
        can_redo: false,
      }))
      toast.success('Task updated')
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update task')
    },
  })
}

export function useToggleDone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, done }: { id: number; done: boolean }) => tasksApi.setDone(id, done),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) =>
          t.id === vars.id
            ? {
                ...t,
                done: vars.done,
                subtasks: t.subtasks.map((s) => ({
                  ...s,
                  done: vars.done,
                  urgent: vars.done ? false : s.urgent,
                })),
              }
            : t
        ),
        can_undo: true,
        can_redo: false,
      }))
      toast.success(vars.done ? 'Task completed' : 'Task unmarked')
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update task')
    },
    onSuccess: (_task, vars) => {
      // The streak/heatmap panel is derived from the server's activity log
      // (a 'completed' entry only exists once the request actually lands),
      // so it refetches on settle rather than being guessed optimistically.
      if (vars.done) queryClient.invalidateQueries({ queryKey: STATS_KEY })
    },
  })
}

export function useSetPinned() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, pinned }: { id: number; pinned: boolean }) => tasksApi.setPinned(id, pinned),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, pinned: vars.pinned } : t)),
        can_undo: true,
        can_redo: false,
      }))
      toast(vars.pinned ? '📌 Task pinned' : '📌 Task unpinned')
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update pin')
    },
  })
}

export function useSetPosition() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, position }: { id: number; position: number }) => tasksApi.setPosition(id, position),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, position: vars.position } : t)),
        can_undo: true,
        can_redo: false,
      }))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to reorder task')
    },
  })
}

export function useSetTaskUrgent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, urgent }: { id: number; urgent: boolean }) => tasksApi.setUrgent(id, urgent),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, urgent: vars.urgent } : t)),
        can_undo: true,
        can_redo: false,
      }))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update urgent flag')
    },
  })
}

export function useAssignTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, assignedTaskId }: { id: number; assignedTaskId: number | null }) =>
      tasksApi.assign(id, assignedTaskId),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, assigned_task_id: vars.assignedTaskId } : t)),
        can_undo: true,
        can_redo: false,
      }))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to assign task')
    },
  })
}

export function useSetDueDate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dueDate }: { id: number; dueDate: string | null }) => tasksApi.setDueDate(id, dueDate),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, due_date: vars.dueDate } : t)),
        can_undo: true,
        can_redo: false,
      }))
      toast.success('Due date updated')
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update due date')
    },
  })
}

// Deliberately doesn't go through beginOptimisticUpdate: notes autosave on a
// debounce while typing, and pushing an undo-stack snapshot on every save
// (see undoRedoStack.ts) would flood the 20-entry stack with near-identical
// in-progress drafts, pushing out the structural edits a user would
// actually want to undo. Matches the backend's set_task_notes, which skips
// save_snapshot() for the same reason. can_undo/can_redo are left untouched
// (no snapshot was pushed, so nothing about undo availability changed).
export function useSetTaskNotes() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, notes }: { id: number; notes: string }) => tasksApi.setNotes(id, notes),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: TASKS_KEY })
      const previous = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
      setTasksData(queryClient, (old) => ({
        ...old,
        tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, notes: vars.notes } : t)),
      }))
      markDirty()
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to save notes')
    },
  })
}

export function useDeleteTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => tasksApi.remove(id),
    onMutate: async (id) => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.filter((t) => t.id !== id),
        can_undo: true,
        can_redo: false,
      }))
      toast('🗑️ Task deleted')
      return { previous }
    },
    onError: (_err, _id, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to delete task')
    },
  })
}

export function useMarkAllCompleted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => tasksApi.markAllCompleted(),
    onMutate: async () => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) => ({
          ...t,
          done: true,
          subtasks: t.subtasks.map((s) => ({ ...s, done: true, urgent: false })),
        })),
        can_undo: true,
        can_redo: false,
      }))
      toast.success('Marked all as completed')
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to mark all completed')
    },
  })
}

export function useClearCompleted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => tasksApi.clearCompleted(),
    onMutate: async () => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.filter((t) => !t.done),
        can_undo: true,
        can_redo: false,
      }))
      toast('🧹 Cleared completed tasks')
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to clear completed tasks')
    },
  })
}

export function useClearAll() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => tasksApi.clearAll(),
    onMutate: async () => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, () => ({ tasks: [], can_undo: true, can_redo: false }))
      toast('🗑️ Cleared all tasks')
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to clear all tasks')
    },
  })
}
