import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { tasksApi } from '../api/tasks'
import type { Task, TasksResponse } from '../types'

export const TASKS_KEY = ['tasks']

// Shared by every mutation below: cancel any in-flight refetch (so it can't
// clobber our optimistic write when it resolves), snapshot the current cache
// for rollback, then hand the caller the previous data to build the
// optimistic update from.
async function beginOptimisticUpdate(queryClient: QueryClient) {
  await queryClient.cancelQueries({ queryKey: TASKS_KEY })
  return queryClient.getQueryData<TasksResponse>(TASKS_KEY)
}

function setTasksData(queryClient: QueryClient, updater: (old: TasksResponse) => TasksResponse) {
  queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) => (old ? updater(old) : old))
}

function rollback(queryClient: QueryClient, previous: TasksResponse | undefined) {
  if (previous) queryClient.setQueryData(TASKS_KEY, previous)
}

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
        subtasks: [],
      }
      setTasksData(queryClient, (old) => ({
        tasks: [optimisticTask, ...old.tasks],
        can_undo: true,
        can_redo: false,
      }))
      return { previous, tempId }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to add task')
    },
    onSuccess: (task, _vars, ctx) => {
      setTasksData(queryClient, (old) => ({
        ...old,
        tasks: old.tasks.map((t) => (t.id === ctx?.tempId ? { ...task, subtasks: [] } : t)),
      }))
      toast.success('Task added')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
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
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update task')
    },
    onSuccess: () => toast.success('Task updated'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASKS_KEY }),
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
            ? { ...t, done: vars.done, subtasks: t.subtasks.map((s) => ({ ...s, done: vars.done })) }
            : t
        ),
        can_undo: true,
        can_redo: false,
      }))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update task')
    },
    onSuccess: (task) => toast.success(task.done ? 'Task completed' : 'Task unmarked'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASKS_KEY }),
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
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update pin')
    },
    onSuccess: (task) => toast(task.pinned ? '📌 Task pinned' : '📌 Task unpinned'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASKS_KEY }),
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
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASKS_KEY }),
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
      return { previous }
    },
    onError: (_err, _id, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to delete task')
    },
    onSuccess: () => toast('🗑️ Task deleted'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASKS_KEY }),
  })
}

export function useMarkAllCompleted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => tasksApi.markAllCompleted(),
    onMutate: async () => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) => ({ ...t, done: true, subtasks: t.subtasks.map((s) => ({ ...s, done: true })) })),
        can_undo: true,
        can_redo: false,
      }))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to mark all completed')
    },
    onSuccess: () => toast.success('Marked all as completed'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASKS_KEY }),
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
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to clear completed tasks')
    },
    onSuccess: () => toast('🧹 Cleared completed tasks'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASKS_KEY }),
  })
}

export function useClearAll() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => tasksApi.clearAll(),
    onMutate: async () => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, () => ({ tasks: [], can_undo: true, can_redo: false }))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to clear all tasks')
    },
    onSuccess: () => toast('🗑️ Cleared all tasks'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASKS_KEY }),
  })
}
