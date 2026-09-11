import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { subtasksApi } from '../api/subtasks'
import { TASKS_KEY, isOwnedTask, beginSharedOptimisticUpdate, setSharedData, rollbackShared } from './useTasks'
import { pushUndoSnapshot } from './undoRedoStack'
import { markDirty } from './saveState'
import type { Task, TasksResponse } from '../types'

async function beginOptimisticUpdate(queryClient: ReturnType<typeof useQueryClient>) {
  await queryClient.cancelQueries({ queryKey: TASKS_KEY })
  const previous = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
  if (previous) pushUndoSnapshot(previous)
  return previous
}

function rollback(queryClient: ReturnType<typeof useQueryClient>, previous: TasksResponse | undefined) {
  if (previous) queryClient.setQueryData(TASKS_KEY, previous)
}

// True when `subtaskId` belongs to a task in the owner's own TASKS_KEY cache
// - false means it's on a collaborator-accessed assignment (SHARED_KEY).
// Unlike isOwnedTask (useTasks.ts), these mutations only ever receive a
// subtaskId, not the parent taskId, so membership has to be found this way.
function isSubtaskOwned(queryClient: ReturnType<typeof useQueryClient>, subtaskId: number): boolean {
  const data = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
  return !!data?.tasks.some((t) => t.subtasks.some((s) => s.id === subtaskId))
}

// A plain counter rather than -Date.now(): pasting a multi-line list adds
// several subtasks in the same synchronous loop (see TaskCard's paste
// handler), and Date.now()'s millisecond resolution isn't fine-grained
// enough to stay unique across those - colliding temp ids became colliding
// React keys, which silently dropped/duplicated rows.
let tempSubtaskSeq = 0

export function useAddSubtask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, text }: { taskId: number; text: string }) => subtasksApi.create(taskId, text),
    onMutate: async (vars) => {
      const tempId = -(++tempSubtaskSeq)
      const clientKey = `temp-subtask-${tempId}`
      const optimisticSubtask = {
        id: tempId,
        task_id: vars.taskId,
        text: vars.text,
        done: false,
        created_at: new Date().toISOString(),
        urgent: false,
        due_date: null,
        notes: null,
        assigned_username: null,
        clientKey,
      }
      toast('➕ Subtask added')
      if (isOwnedTask(queryClient, vars.taskId)) {
        const previous = await beginOptimisticUpdate(queryClient)
        queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
          old
            ? {
                tasks: old.tasks.map((t) =>
                  t.id === vars.taskId ? { ...t, done: false, subtasks: [...t.subtasks, optimisticSubtask] } : t
                ),
                can_undo: true,
                can_redo: false,
              }
            : old
        )
        return { previous, shared: false, tempId, clientKey }
      }
      const previous = await beginSharedOptimisticUpdate(queryClient)
      setSharedData(queryClient, (old) =>
        old.map((t) => (t.id === vars.taskId ? { ...t, done: false, subtasks: [...t.subtasks, optimisticSubtask] } : t))
      )
      return { previous, shared: true, tempId, clientKey }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to add subtask')
    },
    onSuccess: (res, vars, ctx) => {
      // Swap the temp placeholder for the server's real subtask record,
      // keeping the same clientKey so the React key stays stable (see the
      // matching comment in useAddTask for why that matters).
      const patch = (t: Task) =>
        t.id === vars.taskId
          ? {
              ...t,
              subtasks: t.subtasks.map((s) =>
                s.id === ctx?.tempId && res.subtask ? { ...res.subtask, clientKey: ctx.clientKey } : s
              ),
            }
          : t
      if (ctx?.shared) {
        setSharedData(queryClient, (old) => old.map(patch))
      } else {
        queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) => (old ? { ...old, tasks: old.tasks.map(patch) } : old))
      }
    },
  })
}

// Mirrors the backend's set_subtask_done cascade exactly: an uncheck always
// uncompletes the parent; a check only completes it once every subtask is
// done; otherwise the parent's done state is untouched. Shared verbatim by
// both the owner and collaborator optimistic-update branches below.
function applySubtaskDone<T extends Task>(t: T, subtaskId: number, done: boolean): T {
  if (!t.subtasks.some((s) => s.id === subtaskId)) return t
  const subtasks = t.subtasks.map((s) => (s.id === subtaskId ? { ...s, done, urgent: done ? false : s.urgent } : s))
  let parentDone = t.done
  if (!done) parentDone = false
  else if (subtasks.every((s) => s.done)) parentDone = true
  return { ...t, subtasks, done: parentDone }
}

export function useToggleSubtask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ subtaskId, done }: { subtaskId: number; done: boolean }) =>
      subtasksApi.setDone(subtaskId, done),
    onMutate: async (vars) => {
      if (isSubtaskOwned(queryClient, vars.subtaskId)) {
        const previous = await beginOptimisticUpdate(queryClient)
        queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
          old
            ? {
                tasks: old.tasks.map((t) => applySubtaskDone(t, vars.subtaskId, vars.done)),
                can_undo: true,
                can_redo: false,
              }
            : old
        )
        return { previous, shared: false }
      }
      const previous = await beginSharedOptimisticUpdate(queryClient)
      setSharedData(queryClient, (old) => old.map((t) => applySubtaskDone(t, vars.subtaskId, vars.done)))
      return { previous, shared: true }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to update subtask')
    },
  })
}

// Collaborator-accessible, same reasoning/dual-path shape as
// useToggleSubtask above - the workspace's mini task panel is exactly where
// this is used, by owner and collaborator alike.
export function useSetSubtaskAssignee() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ subtaskId, assignedUsername }: { subtaskId: number; assignedUsername: string | null }) =>
      subtasksApi.setAssignee(subtaskId, assignedUsername),
    onMutate: async (vars) => {
      const apply = (t: Task): Task =>
        t.subtasks.some((s) => s.id === vars.subtaskId)
          ? {
              ...t,
              subtasks: t.subtasks.map((s) =>
                s.id === vars.subtaskId ? { ...s, assigned_username: vars.assignedUsername } : s
              ),
            }
          : t
      if (isSubtaskOwned(queryClient, vars.subtaskId)) {
        const previous = await beginOptimisticUpdate(queryClient)
        queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
          old ? { tasks: old.tasks.map(apply), can_undo: true, can_redo: false } : old
        )
        return { previous, shared: false }
      }
      const previous = await beginSharedOptimisticUpdate(queryClient)
      setSharedData(queryClient, (old) => old.map(apply))
      return { previous, shared: true }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to update assignee')
    },
  })
}

export function useSetSubtaskUrgent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ subtaskId, urgent }: { subtaskId: number; urgent: boolean }) =>
      subtasksApi.setUrgent(subtaskId, urgent),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old
          ? {
              tasks: old.tasks.map((t) =>
                t.subtasks.some((s) => s.id === vars.subtaskId)
                  ? {
                      ...t,
                      subtasks: t.subtasks.map((s) =>
                        s.id === vars.subtaskId ? { ...s, urgent: vars.urgent } : s
                      ),
                    }
                  : t
              ),
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

export function useSetSubtaskDueDate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ subtaskId, dueDate }: { subtaskId: number; dueDate: string | null }) =>
      subtasksApi.setDueDate(subtaskId, dueDate),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old
          ? {
              tasks: old.tasks.map((t) =>
                t.subtasks.some((s) => s.id === vars.subtaskId)
                  ? {
                      ...t,
                      subtasks: t.subtasks.map((s) =>
                        s.id === vars.subtaskId ? { ...s, due_date: vars.dueDate } : s
                      ),
                    }
                  : t
              ),
              can_undo: true,
              can_redo: false,
            }
          : old
      )
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
// would flood the 20-entry stack with near-identical in-progress drafts.
// Matches the backend's set_subtask_notes, which skips save_snapshot() for
// the same reason (see useTasks.ts's useSetTaskNotes for the task-notes
// equivalent).
export function useSetSubtaskNotes() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ subtaskId, notes }: { subtaskId: number; notes: string }) =>
      subtasksApi.setNotes(subtaskId, notes),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: TASKS_KEY })
      const previous = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old
          ? {
              ...old,
              tasks: old.tasks.map((t) =>
                t.subtasks.some((s) => s.id === vars.subtaskId)
                  ? {
                      ...t,
                      subtasks: t.subtasks.map((s) =>
                        s.id === vars.subtaskId ? { ...s, notes: vars.notes } : s
                      ),
                    }
                  : t
              ),
            }
          : old
      )
      markDirty()
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to save notes')
    },
  })
}

// Mirrors the backend's delete_subtask: only ever promotes to done once
// every remaining subtask is done, never demotes. Shared verbatim by both
// the owner and collaborator optimistic-update branches below.
function applySubtaskDelete<T extends Task>(t: T, subtaskId: number): T {
  if (!t.subtasks.some((s) => s.id === subtaskId)) return t
  const subtasks = t.subtasks.filter((s) => s.id !== subtaskId)
  const done = subtasks.length > 0 && subtasks.every((s) => s.done) ? true : t.done
  return { ...t, subtasks, done }
}

export function useDeleteSubtask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (subtaskId: number) => subtasksApi.remove(subtaskId),
    onMutate: async (subtaskId) => {
      toast('🗑️ Subtask deleted')
      if (isSubtaskOwned(queryClient, subtaskId)) {
        const previous = await beginOptimisticUpdate(queryClient)
        queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
          old
            ? { tasks: old.tasks.map((t) => applySubtaskDelete(t, subtaskId)), can_undo: true, can_redo: false }
            : old
        )
        return { previous, shared: false }
      }
      const previous = await beginSharedOptimisticUpdate(queryClient)
      setSharedData(queryClient, (old) => old.map((t) => applySubtaskDelete(t, subtaskId)))
      return { previous, shared: true }
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to delete subtask')
    },
  })
}
