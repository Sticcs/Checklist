import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { tasksApi } from '../api/tasks'
import { ApiError } from '../api/client'
import type { LinkItem, Task, TasksResponse, WorkspacePage } from '../types'
import { pushUndoSnapshot, discardLastPushedSnapshot } from './undoRedoStack'
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
//
// Deliberately synchronous, not `await`-ing cancelQueries - this runs
// inside onMutate, and an await here (even just one microtask's worth)
// opens a window where a second mutation fired in the same tick (e.g. two
// checkboxes ticked back-to-back) reads `previous` before the first one's
// optimistic write has landed, then overwrites it when it writes its own -
// silently losing the first toggle. cancelQueries' own cancellation still
// happens (its promise just isn't awaited), only the read-then-write below
// needs to be atomic with respect to the click that triggered it.
function beginOptimisticUpdate(queryClient: QueryClient) {
  void queryClient.cancelQueries({ queryKey: TASKS_KEY })
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
// isn't even visible to a collaborator). Synchronous for the same reason as
// beginOptimisticUpdate above - see its comment.
export function beginSharedOptimisticUpdate(queryClient: QueryClient) {
  void queryClient.cancelQueries({ queryKey: SHARED_KEY })
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
      linkedTaskId,
    }: {
      text: string
      priority: string
      category: string
      dueDate: string | null
      listId?: number | null
      linkedTaskId?: number | null
    }) => tasksApi.create(text, priority, category, dueDate, listId ?? null, linkedTaskId ?? null),
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
      const previous = beginOptimisticUpdate(queryClient)
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
        last_edited_by: null,
        last_edited_at: null,
        linked_task_id: vars.linkedTaskId ?? null,
        carried_over: false,
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
      const previous = beginOptimisticUpdate(queryClient)
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

// Mirrors the backend's _propagate_linked_task_done (see crud.set_done) -
// an expiry list's copied task and its original source task (see
// AddFromListModal/Task.linked_task_id) toggle together, in either
// direction. Never chained (the picker only ever copies from a plain
// main/custom list, never another expiry list), so one pass is enough.
function applyLinkedToggleDone(tasks: Task[], toggledId: number, done: boolean): Task[] {
  const toggled = tasks.find((t) => t.id === toggledId)
  const linkedId = toggled?.linked_task_id ?? null
  return tasks.map((t) =>
    t.id === toggledId || t.id === linkedId || t.linked_task_id === toggledId ? applyToggleDone(t, done) : t
  )
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
        const previous = beginOptimisticUpdate(queryClient)
        setTasksData(queryClient, (old) => ({
          tasks: applyLinkedToggleDone(old.tasks, vars.id, vars.done),
          can_undo: true,
          can_redo: false,
        }))
        return { previous, shared: false }
      }
      const previous = beginSharedOptimisticUpdate(queryClient)
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
      const previous = beginOptimisticUpdate(queryClient)
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
      const previous = beginOptimisticUpdate(queryClient)
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
      const previous = beginOptimisticUpdate(queryClient)
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
      const previous = beginOptimisticUpdate(queryClient)
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
        const previous = beginOptimisticUpdate(queryClient)
        setTasksData(queryClient, (old) => ({
          tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, links: vars.links } : t)),
          can_undo: true,
          can_redo: false,
        }))
        return { previous, shared: false }
      }
      const previous = beginSharedOptimisticUpdate(queryClient)
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

// Only the collaborator who added a link may hide/unhide it (enforced
// server-side), and the response (via applyServerTask, defined below) is
// the server's own filtered view - but the toggling user is always that
// link's own adder, so it never disappears from *their* view regardless of
// hidden state, which makes a plain client-side toggle safe to predict
// immediately instead of waiting on the round-trip the way the pages
// endpoints below have to (those predict a server-generated id, this only
// flips a bool on an id the client already has).
function applyLinkHidden<T extends Task>(t: T, linkId: string, hidden: boolean): T {
  if (!t.links.some((l) => l.id === linkId)) return t
  return { ...t, links: t.links.map((l) => (l.id === linkId ? { ...l, hidden } : l)) }
}

export function useSetLinkHidden() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, linkId, hidden }: { id: number; linkId: string; hidden: boolean }) =>
      tasksApi.setLinkHidden(id, linkId, hidden),
    onMutate: async (vars) => {
      if (isOwnedTask(queryClient, vars.id)) {
        const previous = beginOptimisticUpdate(queryClient)
        setTasksData(queryClient, (old) => ({
          tasks: old.tasks.map((t) => (t.id === vars.id ? applyLinkHidden(t, vars.linkId, vars.hidden) : t)),
          can_undo: true,
          can_redo: false,
        }))
        return { previous, shared: false }
      }
      const previous = beginSharedOptimisticUpdate(queryClient)
      setSharedData(queryClient, (old) =>
        old.map((t) => (t.id === vars.id ? applyLinkHidden(t, vars.linkId, vars.hidden) : t))
      )
      return { previous, shared: true }
    },
    onSuccess: (task) => applyServerTask(queryClient, task),
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to update link visibility')
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
      const previous = beginSharedOptimisticUpdate(queryClient)
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

// Structural page edits (add/delete/rename) - unlike useSetTaskPages above,
// these go through the normal beginOptimisticUpdate/pushUndoSnapshot path
// (so Ctrl+Z actually restores a deleted or renamed page), since each is a
// genuine one-shot action, not a per-keystroke autosave. onSuccess always
// writes back the task the server actually returned (the authoritative
// post-add/delete/rename `pages` array, with the real server-generated id
// for a new page) - but onMutate *also* predicts the change immediately, the
// same way every other structural mutation in this file does, so the page
// tab bar updates the instant you click instead of waiting on the round
// trip. Page tabs have no AnimatePresence/key-based mount animation (unlike
// tasks/subtasks), so a temp id swapping for the real one on success is a
// plain instant DOM update, not a flicker risk worth a clientKey for.
function applyServerTask(queryClient: QueryClient, task: Task) {
  if (isOwnedTask(queryClient, task.id)) {
    setTasksData(queryClient, (old) => ({ ...old, tasks: old.tasks.map((t) => (t.id === task.id ? task : t)) }))
  } else {
    setSharedData(queryClient, (old) => old.map((t) => (t.id === task.id ? task : t)))
  }
}

// Mirrors AssignmentWorkspace's own defaultFirstPage/backend's
// _effective_pages: a task whose `pages` column has never actually been
// saved (every brand-new assignment, until its first structural page edit
// or debounced content save) reports pages:[] from the server, with "Page
// 1" only synthesized client-side in local component state - never written
// back to this cache. Predicting an add/rename against the raw (possibly
// still-empty) t.pages would silently drop or no-op against that implicit
// page; this reproduces the same synthesis so the optimistic update
// matches what the user already sees on screen.
function effectivePages(t: Task): WorkspacePage[] {
  return t.pages.length > 0 ? t.pages : [{ id: 'page-1', title: 'Page 1', content: t.notes ?? '' }]
}

function applyOptimisticPageChange(
  queryClient: QueryClient,
  taskId: number,
  apply: (t: Task) => Task
): { previous: TasksResponse | Task[] | undefined; shared: boolean } {
  if (isOwnedTask(queryClient, taskId)) {
    const previous = beginOptimisticUpdate(queryClient)
    setTasksData(queryClient, (old) => ({ ...old, tasks: old.tasks.map((t) => (t.id === taskId ? apply(t) : t)) }))
    return { previous, shared: false }
  }
  const previous = beginSharedOptimisticUpdate(queryClient)
  setSharedData(queryClient, (old) => old.map((t) => (t.id === taskId ? apply(t) : t)))
  return { previous, shared: true }
}

export function useAddPage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) => tasksApi.addPage(id, title),
    onMutate: async (vars) => {
      const tempPage: WorkspacePage = { id: `temp-page-${Date.now()}`, title: vars.title, content: '' }
      return applyOptimisticPageChange(queryClient, vars.id, (t) => ({ ...t, pages: [...effectivePages(t), tempPage] }))
    },
    onSuccess: (task) => applyServerTask(queryClient, task),
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to add page')
    },
  })
}

export function useDeletePage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, pageId }: { id: number; pageId: string }) => tasksApi.deletePage(id, pageId),
    onMutate: async (vars) => {
      // Mirrors the backend's own refusal - optimistically removing the
      // last page would show an empty tab bar for a moment before the
      // server's refusal response puts it right back.
      return applyOptimisticPageChange(queryClient, vars.id, (t) => {
        const pages = effectivePages(t)
        return pages.length > 1 ? { ...t, pages: pages.filter((p) => p.id !== vars.pageId) } : { ...t, pages }
      })
    },
    onSuccess: (task) => applyServerTask(queryClient, task),
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to delete page')
    },
  })
}

export function useRenamePage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, pageId, title }: { id: number; pageId: string; title: string }) =>
      tasksApi.renamePage(id, pageId, title),
    onMutate: async (vars) => {
      return applyOptimisticPageChange(queryClient, vars.id, (t) => ({
        ...t,
        pages: effectivePages(t).map((p) => (p.id === vars.pageId ? { ...p, title: vars.title } : p)),
      }))
    },
    onSuccess: (task) => applyServerTask(queryClient, task),
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to rename page')
    },
  })
}

// Version-history panel's list fetch - only enabled while the panel is
// actually open (see AssignmentWorkspace's historyOpen), not polled
// alongside everything else, since it's only relevant while someone is
// actively looking at it.
export function usePageVersions(taskId: number, pageId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['page-versions', taskId, pageId],
    queryFn: () => tasksApi.listPageVersions(taskId, pageId),
    enabled,
  })
}

export function useRestorePageVersion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, pageId, versionId }: { id: number; pageId: string; versionId: number }) =>
      tasksApi.restorePageVersion(id, pageId, versionId),
    onMutate: async (vars) => {
      if (isOwnedTask(queryClient, vars.id)) return { previous: beginOptimisticUpdate(queryClient), shared: false }
      return { previous: beginSharedOptimisticUpdate(queryClient), shared: true }
    },
    onSuccess: (task) => applyServerTask(queryClient, task),
    onError: (_err, _vars, ctx) => {
      if (ctx?.shared) rollbackShared(queryClient, ctx.previous as Task[] | undefined)
      else rollback(queryClient, ctx?.previous as TasksResponse | undefined)
      toast.error('Failed to restore version')
    },
  })
}

export function useAssignTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, assignedTaskId }: { id: number; assignedTaskId: number | null }) =>
      tasksApi.assign(id, assignedTaskId),
    onMutate: async (vars) => {
      const previous = beginOptimisticUpdate(queryClient)
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
      const previous = beginOptimisticUpdate(queryClient)
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

export function useMoveTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, listId }: { id: number; listId: number }) => tasksApi.setListId(id, listId),
    onMutate: async (vars) => {
      const previous = beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.map((t) => (t.id === vars.id ? { ...t, list_id: vars.listId } : t)),
        can_undo: true,
        can_redo: false,
      }))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      rollback(queryClient, ctx?.previous)
      toast.error('Failed to move task')
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
      const previous = beginOptimisticUpdate(queryClient)
      setTasksData(queryClient, (old) => ({
        tasks: old.tasks.filter((t) => t.id !== id),
        can_undo: true,
        can_redo: false,
      }))
      toast('🗑️ Task deleted')
      return { previous }
    },
    onError: (err, _id, ctx) => {
      if (err instanceof ApiError && err.status === 404) {
        // Already gone server-side (a double-click, another tab, a
        // cascading delete from clearing/removing its list) - the
        // optimistic removal was actually correct, so leave it removed
        // instead of reviving a ghost the server has no record of. The
        // route 404s before crud.delete_task/save_snapshot ever runs, so
        // the undo snapshot pushed for this delete has no server-side
        // counterpart either - discarded here so the mirror doesn't end up
        // one entry ahead of the server's real stack (see
        // discardLastPushedSnapshot's comment).
        discardLastPushedSnapshot()
        queryClient.invalidateQueries({ queryKey: TASKS_KEY })
        return
      }
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
      const previous = beginOptimisticUpdate(queryClient)
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
      const previous = beginOptimisticUpdate(queryClient)
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
      const previous = beginOptimisticUpdate(queryClient)
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
