import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { tasksApi } from '../api/tasks'
import { ApiError } from '../api/client'
import type { LinkItem, Task, TasksResponse, WorkspacePage } from '../types'
import { pushUndoSnapshot } from './undoRedoStack'
import { markDirty } from './saveState'
import { STATS_KEY } from './useStats'
import { SHOPPING_CATEGORY } from '../constants'
import { addToOutbox } from '../lib/offlineOutbox'

export const TASKS_KEY = ['tasks']
// A collaborator's view of assignments they don't own (see
// hooks/useCollaboration.ts's useSharedWithMe) - a plain Task[], unlike
// TASKS_KEY's {tasks, can_undo, can_redo} shape, since a collaborator has no
// undo/redo stack of their own for someone else's task. Defined here (not in
// useCollaboration.ts) because the mutation hooks below need it, and
// useCollaboration.ts already needs to import from here - keeping it here
// avoids a circular import.
export const SHARED_KEY = ['shared-with-me']

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

// True when `taskId` is in the signed-in user's own TASKS_KEY cache (i.e.
// they own it) - false means it's a collaborator-accessed assignment (see
// SHARED_KEY), which every dual-path mutation hook below branches on. This
// is deliberately a cache lookup, not an API call: TaskListPage always has
// both caches populated before either the main list or a workspace can be
// interacted with, so the cache is authoritative for "which list is this
// task actually in right now" without an extra round-trip.
export function isOwnedTask(queryClient: QueryClient, taskId: number): boolean {
  const data = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
  return !!data?.tasks.some((t) => t.id === taskId)
}

// SHARED_KEY equivalents of beginOptimisticUpdate/setTasksData/rollback
// above - deliberately lighter: no pushUndoSnapshot, since a collaborator's
// edits to someone else's assignment have nothing to do with the owner's own
// undo/redo stack (which is fetched from the owner's own /api/tasks and
// isn't even visible to a collaborator).
export async function beginSharedOptimisticUpdate(queryClient: QueryClient) {
  await queryClient.cancelQueries({ queryKey: SHARED_KEY })
  return queryClient.getQueryData<Task[]>(SHARED_KEY)
}

export function setSharedData(queryClient: QueryClient, updater: (old: Task[]) => Task[]) {
  queryClient.setQueryData<Task[]>(SHARED_KEY, (old) => (old ? updater(old) : old))
}

export function rollbackShared(queryClient: QueryClient, previous: Task[] | undefined) {
  if (previous) queryClient.setQueryData(SHARED_KEY, previous)
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
      listId,
    }: {
      text: string
      priority: string
      category: string
      dueDate: string | null
      listId?: number | null
    }) => tasksApi.create(text, priority, category, dueDate, listId ?? null),
    // Without this, TanStack Query's default networkMode ('online') PAUSES
    // the mutation the moment navigator.onLine is false, instead of
    // actually attempting (and failing) the request - mutationFn is simply
    // never called until the browser reports back online, so onError below
    // (which is what feeds the offline outbox) never fires, and a page
    // reload while that pause is in effect loses the whole thing silently.
    // 'always' makes it behave the way a plain fetch does: try for real,
    // fail for real, so the outbox actually gets a chance to catch it.
    networkMode: 'always',
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
        in_progress: false,
        links: [],
        pages: [],
        subtasks: [],
        list_id: vars.listId ?? null,
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
    onError: (err, vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      if (err instanceof ApiError) {
        toast.error('Failed to add task')
        return
      }
      // A network failure (offline, unreachable, etc.), not a real
      // rejection from the server - the typed text is real work the user
      // shouldn't have to redo, so it's queued instead of just discarded;
      // useOfflineSync replays it the moment connectivity returns.
      addToOutbox({ kind: 'task', label: vars.text, payload: vars })
      toast.warning(`Offline — "${vars.text}" will be added once you're back online.`)
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

// Mirrors the backend's set_done cascade (completing clears in_progress and
// cascades to subtasks) - shared verbatim by both the owner and collaborator
// optimistic-update branches below, since the server-side effect is
// identical either way, only which cache holds the task differs.
function applyToggleDone<T extends Task>(t: T, done: boolean): T {
  return {
    ...t,
    done,
    in_progress: done ? false : t.in_progress,
    subtasks: t.subtasks.map((s) => ({ ...s, done, urgent: done ? false : s.urgent })),
  }
}

// Looks a task up by id across both caches, purely to read its category for
// the toast message below - a Shopping item being checked off isn't a "task
// completed" the way a to-do or assignment is.
function findTaskInCache(queryClient: QueryClient, id: number): Task | undefined {
  return (
    queryClient.getQueryData<TasksResponse>(TASKS_KEY)?.tasks.find((t) => t.id === id) ??
    queryClient.getQueryData<Task[]>(SHARED_KEY)?.find((t) => t.id === id)
  )
}

export function useToggleDone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, done }: { id: number; done: boolean }) => tasksApi.setDone(id, done),
    onMutate: async (vars) => {
      const isShoppingItem = findTaskInCache(queryClient, vars.id)?.category === SHOPPING_CATEGORY
      const message = isShoppingItem
        ? vars.done
          ? '🛒 Got it!'
          : '↩️ Back on the list'
        : vars.done
          ? 'Task completed'
          : 'Task unmarked'
      toast.success(message)
      if (isOwnedTask(queryClient, vars.id)) {
        const previous = await beginOptimisticUpdate(queryClient)
        setTasksData(queryClient, (old) => ({
          tasks: old.tasks.map((t) => (t.id === vars.id ? applyToggleDone(t, vars.done) : t)),
          can_undo: true,
          can_redo: false,
        }))
        return { previous, shared: false }
      }
      const previous = await beginSharedOptimisticUpdate(queryClient)
      setSharedData(queryClient, (old) => old.map((t) => (t.id === vars.id ? applyToggleDone(t, vars.done) : t)))
      return { previous, shared: true }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to update task')
    },
    onSuccess: (_task, vars, ctx) => {
      // The streak/heatmap panel is derived from the server's activity log
      // (a 'completed' entry only exists once the request actually lands),
      // so it refetches on settle rather than being guessed optimistically.
      // Only meaningful for the owner's own stats - a collaborator
      // completing someone else's assignment doesn't touch their own streak.
      if (vars.done && !ctx?.shared) queryClient.invalidateQueries({ queryKey: STATS_KEY })
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

export function useSetTaskInProgress() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, inProgress }: { id: number; inProgress: boolean }) =>
      tasksApi.setInProgress(id, inProgress),
    onMutate: async (vars) => {
      const previous = await beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, in_progress: vars.inProgress } : t)),
        can_undo: true,
        can_redo: false,
      }))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to update progress status')
    },
  })
}

export function useSetTaskLinks() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, links }: { id: number; links: LinkItem[] }) => tasksApi.setLinks(id, links),
    onMutate: async (vars) => {
      if (isOwnedTask(queryClient, vars.id)) {
        const previous = await beginOptimisticUpdate(queryClient)
        setTasksData(queryClient, (old) => ({
          tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, links: vars.links } : t)),
          can_undo: true,
          can_redo: false,
        }))
        return { previous, shared: false }
      }
      const previous = await beginSharedOptimisticUpdate(queryClient)
      setSharedData(queryClient, (old) => old.map((t) => (t.id === vars.id ? { ...t, links: vars.links } : t)))
      return { previous, shared: true }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to update links')
    },
  })
}

// Same "no undo snapshot" reasoning as useSetTaskNotes - the whole pages
// array is re-saved on every debounced keystroke while typing in a page
// (see AssignmentWorkspace), so snapshotting each one would flood the
// undo stack with near-identical in-progress drafts.
export function useSetTaskPages() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, pages }: { id: number; pages: WorkspacePage[] }) => tasksApi.setPages(id, pages),
    // See the matching comment on useAddTask - AssignmentWorkspace's pages
    // autosave retry logic is keyed on onError actually firing while
    // offline, which the default networkMode ('online') never lets happen.
    networkMode: 'always',
    onMutate: async (vars) => {
      markDirty()
      if (isOwnedTask(queryClient, vars.id)) {
        await queryClient.cancelQueries({ queryKey: TASKS_KEY })
        const previous = queryClient.getQueryData<TasksResponse>(TASKS_KEY)
        setTasksData(queryClient, (old) => ({
          ...old,
          tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, pages: vars.pages } : t)),
        }))
        return { previous, shared: false }
      }
      const previous = await beginSharedOptimisticUpdate(queryClient)
      setSharedData(queryClient, (old) => old.map((t) => (t.id === vars.id ? { ...t, pages: vars.pages } : t)))
      return { previous, shared: true }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to save pages')
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
    // See the matching comment on useAddTask - TaskCard's notes-autosave
    // retry logic is keyed on onError actually firing while offline, which
    // the default networkMode ('online') never lets happen.
    networkMode: 'always',
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
          in_progress: false,
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
