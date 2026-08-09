import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useTasks, useToggleDone } from '../hooks/useTasks'
import { useSubtaskFocusHotkey } from '../hooks/useHotkeys'
import { AddTaskForm } from '../components/AddTaskForm'
import { TaskCard } from '../components/TaskCard'
import { ProgressBar } from '../components/ProgressBar'
import { QuoteHeader } from '../components/QuoteHeader'
import { Sidebar, type StatusFilter } from '../components/Sidebar'
import { sortTasks, type SortBy } from '../utils/sortTasks'
import { toISODate } from '../utils/dueDatePresets'
import type { Task } from '../types'

export function TaskListPage() {
  const { data, isLoading, error } = useTasks()
  const toggleDone = useToggleDone()

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('All')
  const [categoryFilter, setCategoryFilter] = useState<string[]>([])
  const [pinnedOnly, setPinnedOnly] = useState(false)
  const [sortBy, setSortBy] = useState<SortBy>('Priority')

  const [armedTaskId, setArmedTaskId] = useState<number | null>(null)
  const [latestTaskId, setLatestTaskId] = useState<number | null>(null)
  const [lastExpandedTaskId, setLastExpandedTaskId] = useState<number | null>(null)

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

  const todayIso = toISODate(new Date())
  const doneCount = tasks.filter((t) => t.done).length

  // Click-to-complete via event delegation: a click lands either inside a
  // card's "content area" (data-task-content-id) - which arms it, or confirms
  // and toggles it if it was already armed - or anywhere else (buttons,
  // expander, blank space), which just disarms whatever was armed.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      const contentArea = target.closest('[data-task-content-id]')
      const clickedId = contentArea ? Number(contentArea.getAttribute('data-task-content-id')) : null

      if (clickedId === null) {
        setArmedTaskId((prev) => (prev !== null ? null : prev))
        return
      }

      setArmedTaskId((prev) => {
        if (prev === clickedId) {
          const task = tasksById.get(clickedId)
          if (task) toggleDone.mutate({ id: clickedId, done: !task.done })
          return null
        }
        return clickedId
      })
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [tasksById, toggleDone])

  useSubtaskFocusHotkey({
    latestTaskId,
    lastExpandedTaskId,
    onConsumeLatest: () => setLatestTaskId(null),
  })

  return (
    <div className="app-layout">
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
      />

      <div className="content-area">
        <div className="task-entry-panel">
          <QuoteHeader />
          <AddTaskForm onAdded={(id) => setLatestTaskId(id)} />
        </div>

        <div className="task-list-column">
          {isLoading && <p className="status-message">Loading...</p>}
          {error && (
            <p className="status-message error" role="alert">
              Failed to load tasks
            </p>
          )}

          <ProgressBar done={doneCount} total={tasks.length} />

          {filtered.length === 0 ? (
            <p className="status-message">No tasks match your filters yet.</p>
          ) : (
            <ul className="task-list">
              <AnimatePresence>
                {filtered.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    armed={armedTaskId === task.id}
                    todayIso={todayIso}
                    onExpandSubtasks={setLastExpandedTaskId}
                  />
                ))}
              </AnimatePresence>
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
