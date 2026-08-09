import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion, Reorder } from 'framer-motion'
import { useSetPosition, useTasks, useToggleDone } from '../hooks/useTasks'
import { useSubtaskFocusHotkey } from '../hooks/useHotkeys'
import { AddTaskForm } from '../components/AddTaskForm'
import { TaskCard } from '../components/TaskCard'
import { ProgressBar } from '../components/ProgressBar'
import { QuoteHeader } from '../components/QuoteHeader'
import { Scratchpad } from '../components/Scratchpad'
import { Sidebar, type StatusFilter } from '../components/Sidebar'
import { sortTasks, type SortBy } from '../utils/sortTasks'
import { toISODate } from '../utils/dueDatePresets'
import type { Task } from '../types'

export function TaskListPage() {
  const { data, isLoading, error } = useTasks()
  const toggleDone = useToggleDone()
  const setPosition = useSetPosition()

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('All')
  const [categoryFilter, setCategoryFilter] = useState<string[]>([])
  const [pinnedOnly, setPinnedOnly] = useState(false)
  const [sortBy, setSortBy] = useState<SortBy>('Priority')

  const [focusedTaskId, setFocusedTaskId] = useState<number | null>(null)
  const [latestTaskId, setLatestTaskId] = useState<number | null>(null)
  const [lastExpandedTaskId, setLastExpandedTaskId] = useState<number | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const tasks = useMemo(() => data?.tasks ?? [], [data])
  const tasksById = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks])

  const availableCategories = useMemo(
    () => Array.from(new Set(tasks.map((t) => t.category))).sort(),
    [tasks]
  )

  // A category that disappears (e.g. after Clear all) shouldn't leave a
  // stale, invalid filter selection sitting around; and a category seen for
  // the first time shouldn't hide the task that just introduced it.
  useEffect(() => {
    setCategoryFilter((prev) => {
      const stillValid = prev.filter((c) => availableCategories.includes(c))
      return stillValid.length === prev.length ? prev : stillValid
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availableCategories.join(',')])

  const filtered = useMemo(() => {
    let result: Task[] = tasks
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      result = result.filter((t) => t.text.toLowerCase().includes(q))
    }
    if (statusFilter === 'Active') result = result.filter((t) => !t.done)
    else if (statusFilter === 'Completed') result = result.filter((t) => t.done)
    if (categoryFilter.length > 0) result = result.filter((t) => categoryFilter.includes(t.category))
    if (pinnedOnly) result = result.filter((t) => t.pinned)
    return sortTasks(result, sortBy)
  }, [tasks, search, statusFilter, categoryFilter, pinnedOnly, sortBy])

  // Local copy driving the drag visuals in Manual mode: framer-motion's
  // Reorder.Group needs a values array it can update continuously as items
  // swap past each other mid-drag, ahead of the position mutation landing.
  const [manualOrder, setManualOrder] = useState<Task[]>(filtered)
  useEffect(() => {
    setManualOrder(filtered)
  }, [filtered])

  const persistPosition = (taskId: number) => {
    const idx = manualOrder.findIndex((t) => t.id === taskId)
    if (idx === -1) return
    const prev = manualOrder[idx - 1]
    const next = manualOrder[idx + 1]
    let position: number
    if (prev && next) position = (prev.position + next.position) / 2
    else if (next) position = next.position - 1
    else if (prev) position = prev.position + 1
    else position = 0
    setPosition.mutate({ id: taskId, position })
  }

  const todayIso = toISODate(new Date())
  const doneCount = tasks.filter((t) => t.done).length

  // Click-to-complete via event delegation: Ctrl/Cmd+click anywhere inside a
  // card's "content area" (data-task-content-id) toggles it done immediately
  // - no confirmation step. A plain click there instead focuses that task
  // (so '/' routes to its subtask input, see useSubtaskFocusHotkey); clicking
  // the already-focused task's content again clears focus, as does clicking
  // anywhere else (buttons, expander, blank space).
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      const contentArea = target.closest('[data-task-content-id]')
      const clickedId = contentArea ? Number(contentArea.getAttribute('data-task-content-id')) : null

      if (clickedId === null) {
        setFocusedTaskId((prev) => (prev !== null ? null : prev))
        return
      }

      if (e.ctrlKey || e.metaKey) {
        const task = tasksById.get(clickedId)
        if (task) toggleDone.mutate({ id: clickedId, done: !task.done })
        return
      }

      setFocusedTaskId((prev) => (prev === clickedId ? null : clickedId))
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [tasksById, toggleDone])

  useSubtaskFocusHotkey({
    focusedTaskId,
    latestTaskId,
    lastExpandedTaskId,
    onConsumeLatest: () => setLatestTaskId(null),
  })

  return (
    <div className="app-layout">
      <AnimatePresence>
        {!sidebarOpen && (
          <motion.button
            type="button"
            className="sidebar-toggle-btn"
            onClick={() => setSidebarOpen(true)}
            title="Open sidebar"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: 0.2 }}
          >
            ☰
          </motion.button>
        )}
      </AnimatePresence>

      <motion.div
        className="sidebar-wrapper"
        animate={{ width: sidebarOpen ? 300 : 0 }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
      >
        <Sidebar
          search={search}
          onSearchChange={setSearch}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          availableCategories={availableCategories}
          categoryFilter={categoryFilter}
          onCategoryFilterChange={setCategoryFilter}
          pinnedOnly={pinnedOnly}
          onPinnedOnlyChange={setPinnedOnly}
          sortBy={sortBy}
          onSortByChange={setSortBy}
          canUndo={data?.can_undo ?? false}
          canRedo={data?.can_redo ?? false}
          hasCompletedTasks={doneCount > 0}
          onClose={() => setSidebarOpen(false)}
        />
      </motion.div>

      <div className="content-area">
        <div className="entry-column">
          <div className="task-entry-panel">
            <QuoteHeader />
            <AddTaskForm onAdded={(id) => setLatestTaskId(id)} hasTasks={tasks.length > 0} />
          </div>
          <Scratchpad />
        </div>

        <div className="task-list-column">
          {isLoading && <p className="status-message">Loading...</p>}
          {error && (
            <p className="status-message error" role="alert">
              Failed to load tasks
            </p>
          )}

          <ProgressBar done={doneCount} total={tasks.length} />

          {/* The list container (and its AnimatePresence) stays mounted even
              when `filtered` is empty, so a just-deleted last item still gets
              to play its exit animation - swapping it out for the "no
              tasks" message the instant the array emptied (the previous
              approach) unmounted AnimatePresence along with it, skipping
              the animation entirely. The empty-state message is additive,
              not a replacement. */}
          {sortBy === 'Manual' ? (
            <Reorder.Group
              as="ul"
              axis="y"
              className="task-list"
              values={manualOrder}
              onReorder={setManualOrder}
            >
              <AnimatePresence>
                {manualOrder.map((task) => (
                  <TaskCard
                    key={task.clientKey ?? task.id}
                    task={task}
                    focused={focusedTaskId === task.id}
                    todayIso={todayIso}
                    onExpandSubtasks={setLastExpandedTaskId}
                    draggable
                    onDragEnd={persistPosition}
                  />
                ))}
              </AnimatePresence>
            </Reorder.Group>
          ) : (
            <ul className="task-list">
              <AnimatePresence>
                {filtered.map((task) => (
                  <TaskCard
                    key={task.clientKey ?? task.id}
                    task={task}
                    focused={focusedTaskId === task.id}
                    todayIso={todayIso}
                    onExpandSubtasks={setLastExpandedTaskId}
                  />
                ))}
              </AnimatePresence>
            </ul>
          )}

          {filtered.length === 0 && <p className="status-message">No tasks match your filters yet.</p>}
        </div>
      </div>
    </div>
  )
}
