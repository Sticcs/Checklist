import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { tasksApi } from '../api/tasks'

export const TASKS_KEY = ['tasks']

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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast.success('Task added')
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast.success('Task updated')
    },
  })
}

export function useToggleDone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, done }: { id: number; done: boolean }) => tasksApi.setDone(id, done),
    onSuccess: (task) => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast.success(task.done ? 'Task completed' : 'Task unmarked')
    },
  })
}

export function useSetPinned() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, pinned }: { id: number; pinned: boolean }) => tasksApi.setPinned(id, pinned),
    onSuccess: (task) => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast(task.pinned ? '📌 Task pinned' : '📌 Task unpinned')
    },
  })
}

export function useDeleteTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => tasksApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast('🗑️ Task deleted')
    },
  })
}

export function useMarkAllCompleted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => tasksApi.markAllCompleted(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast.success('Marked all as completed')
    },
  })
}

export function useClearCompleted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => tasksApi.clearCompleted(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast('🧹 Cleared completed tasks')
    },
  })
}

export function useClearAll() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => tasksApi.clearAll(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast('🗑️ Cleared all tasks')
    },
  })
}
