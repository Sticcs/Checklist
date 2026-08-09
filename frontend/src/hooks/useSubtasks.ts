import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { subtasksApi } from '../api/subtasks'
import { TASKS_KEY } from './useTasks'

export function useAddSubtask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, text }: { taskId: number; text: string }) => subtasksApi.create(taskId, text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast('➕ Subtask added')
    },
  })
}

export function useToggleSubtask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ subtaskId, done }: { subtaskId: number; done: boolean }) =>
      subtasksApi.setDone(subtaskId, done),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TASKS_KEY }),
  })
}

export function useDeleteSubtask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (subtaskId: number) => subtasksApi.remove(subtaskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TASKS_KEY })
      toast('🗑️ Subtask deleted')
    },
  })
}
