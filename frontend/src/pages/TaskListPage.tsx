import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion, Reorder } from 'framer-motion'
import { useSetPosition, useTasks, useToggleDone } from '../hooks/useTasks'
import { useToggleSubtask } from '../hooks/useSubtasks'
import { useIsDesktopApp } from '../hooks/useIsDesktopApp'
import { useWebsiteLinkStatus } from '../hooks/useData'
import { useSubtaskFocusHotkey, useUndoRedoHotkeys } from '../hooks/useHotkeys'
import { useDueDateNotifications } from '../hooks/useDueDateNotifications'
import { AddTaskForm } from '../components/AddTaskForm'
import { TaskCard } from '../components/TaskCard'
import { ProgressBar } from '../components/ProgressBar'
import { QuoteHeader } from '../components/QuoteHeader'
import { Scratchpad } from '../components/Scratchpad'
import { SubtaskNotepad } from '../components/SubtaskNotepad'
import { AssessmentsPanel } from '../components/AssessmentsPanel'
import { KeyboardShortcutsHelp } from '../components/KeyboardShortcutsHelp'
import { Sidebar, type StatusFilter } from '../components/Sidebar'
import { sortTasks, type SortBy } from '../utils/sortTasks'
import { toISODate } from '../utils/dueDatePresets'
import { ASSESSMENT_CATEGORY } from '../constants'
import type { Task } from '../types'

export function TaskListPage() {
  const { data, isLoading, error } = useTasks()
  const toggleDone = useToggleDone()
  const toggleSubtask = useToggleSubtask()
  const setPosition = useSetPosition()
  const isDesktopApp = useIsDesktopApp()
  useWebsiteLinkStatus()

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('All')
  const [categoryFilter, setCategoryFilter] = useState<string[]>([])
  const [pinnedOnly, setPinnedOnly] = useState(false)
  const [sortBy, setSortBy] = useState<SortBy>('Priority')

  const [focusedTaskId, setFocusedTaskId] = useState<number | null>(null)
  const [focusedSubtaskId, setFocusedSubtaskId] = useState<number | null>(null)
  const [notepadHidden, setNotepadHidden] = useState(false)
  const [latestTaskId, setLatestTaskId] = useState<number | null>(null)
  const [lastExpandedTaskId, setLastExpandedTaskId] = useState<number | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const tasks = useMemo(() => data?.tasks ?? [], [data])
  const tasksById = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks])
  const subtasksById = useMemo(() => {
    const m = new Map<number, (typeof tasks)[number]['subtasks'][number]>()
    for (const t of tasks) for (const s of t.subtasks) m.set(s.id, s)
    return m
  }, [tasks])

  const focusedSubtask = focusedSubtaskId !== null ? (subtasksById.get(focusedSubtaskId) ?? null) : null

  // The notepad opens automatically every time focus lands on a (possibly
  // different) subtask - any earlier "hide notepad" choice shouldn't carry
  // over and suppress it for the next one.
  useEffect(() => {
    setNotepadHidden(false)
  }, [focusedSubtaskId])

  // Assessments (category === 'Assessment') live in their own panel, not the
  // main list - everything else about them (mutations, undo/redo, clear
  // completed) is shared, via the same `tasks` entity and the same
  // click-delegation handler below, just filtered into a different view.
  const mainTasks = useMemo(() => tasks.filter((t) => t.category !== ASSESSMENT_CATEGORY), [tasks])
  // Closest due date first; assessments with no due date sort to the end.
  const assessments = useMemo(
    () =>
      tasks
        .filter((t) => t.category === ASSESSMENT_CATEGORY)
        .slice()
        .sort((a, b) => {
          if (a.due_date === b.due_date) return 0
          if (a.due_date === null) return 1
          if (b.due_date === null) return -1
          return a.due_date < b.due_date ? -1 : 1
        }),
    [tasks]
  )

  const availableCategories = useMemo(
    () => Array.from(new Set(mainTasks.map((t) => t.category))).sort(),
    [mainTasks]
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
    let result: Task[] = mainTasks
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      result = result.filter((t) => t.text.toLowerCase().includes(q))
    }
    if (statusFilter === 'Active') result = result.filter((t) => !t.done)
    else if (statusFilter === 'Completed') result = result.filter((t) => t.done)
    if (categoryFilter.length > 0) result = result.filter((t) => categoryFilter.includes(t.category))
    if (pinnedOnly) result = result.filter((t) => t.pinned)
    return sortTasks(result, sortBy)
  }, [mainTasks, search, statusFilter, categoryFilter, pinnedOnly, sortBy])

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
  const doneCount = mainTasks.filter((t) => t.done).length
  const hasAnyCompletedTasks = tasks.some((t) => t.done)

  // Click-to-complete via event delegation: Ctrl/Cmd+click anywhere inside a
  // card's "content area" (data-task-content-id) toggles it done immediately
  // - no confirmation step. A plain click there instead focuses that task
  // (so '/' routes to its subtask input, see useSubtaskFocusHotkey, and its
  // subtasks auto-expand, see TaskCard); clicking the already-focused task's
  // content again clears focus. Focus only clears on a click genuinely
  // outside any task card (data-task-id) - a click elsewhere *within* the
  // focused task's own card (its subtask panel, action buttons) leaves focus
  // alone, since the auto-expanded subtask panel needs to stay open while
  // you're actually interacting with it.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      // The scratchpad and the subtask notepad (plus its expand overlay,
      // portaled onto <body>) live outside any task card's DOM subtree -
      // without this, any click inside them (typing a note, hitting the
      // expand button) reads as "clicked outside every task card" below and
      // immediately clears focus, which for the notepad also means it
      // unmounts itself mid-click since it only renders while a subtask is
      // focused.
      if (target.closest('[data-focus-exempt]')) return
      const taskCard = target.closest('[data-task-id]')
      const contentArea = target.closest('[data-task-content-id]')
      const contentId = contentArea ? Number(contentArea.getAttribute('data-task-content-id')) : null
      // A subtask's own line (its text, not the icon buttons next to it -
      // see the sibling layout in TaskCard) toggles that subtask's focus
      // independently of the parent task's focus. Ctrl/Cmd+click there
      // mirrors the task-level behavior above: toggle done instead of focus.
      const subtaskContentArea = target.closest('[data-subtask-content-id]')
      const subtaskContentId = subtaskContentArea
        ? Number(subtaskContentArea.getAttribute('data-subtask-content-id'))
        : null

      if (!taskCard) {
        setFocusedTaskId((prev) => (prev !== null ? null : prev))
        setFocusedSubtaskId((prev) => (prev !== null ? null : prev))
        return
      }

      if (subtaskContentId !== null) {
        if (e.ctrlKey || e.metaKey) {
          const subtask = subtasksById.get(subtaskContentId)
          if (subtask) toggleSubtask.mutate({ subtaskId: subtaskContentId, done: !subtask.done })
          return
        }
        setFocusedSubtaskId((prev) => (prev === subtaskContentId ? null : subtaskContentId))
        return
      }

      if (contentId === null) {
        // Inside a task card, but not its content area (buttons, subtask
        // panel, drag handle) - nothing to do with focus here.
        return
      }

      // Focus moved to the task's own content - any subtask focus it held
      // is no longer relevant.
      setFocusedSubtaskId((prev) => (prev !== null ? null : prev))

      if (e.ctrlKey || e.metaKey) {
        const task = tasksById.get(contentId)
        if (task) toggleDone.mutate({ id: contentId, done: !task.done })
        return
      }

      setFocusedTaskId((prev) => (prev === contentId ? null : contentId))
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [tasksById, toggleDone, subtasksById, toggleSubtask])

  useSubtaskFocusHotkey({
    focusedTaskId,
    latestTaskId,
    lastExpandedTaskId,
    onConsumeLatest: () => setLatestTaskId(null),
  })
  useUndoRedoHotkeys()
  useDueDateNotifications(tasks)

  return (
    <div className={isDesktopApp ? 'app-layout desktop-app' : 'app-layout'}>
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
          hasCompletedTasks={hasAnyCompletedTasks}
          onClose={() => setSidebarOpen(false)}
        />
      </motion.div>

      <div className="content-area">
        <div className="entry-column">
          <div className="task-entry-panel">
            <QuoteHeader />
            <AddTaskForm onAdded={(id) => setLatestTaskId(id)} hasTasks={mainTasks.length > 0} />
          </div>
          <div className="bottom-panels-row">
            <Scratchpad />
            {/* popLayout: switching focus straight from one subtask to
                another swaps the `key`, so the old notepad is exiting while
                the new one is entering at the same time. Without popLayout
                both compete for the same flex slot while that overlap lasts,
                which staggers/shifts the new one's position for a few
                frames; popLayout pulls the exiting one out of layout flow
                immediately so the new one lands in place right away. */}
            <AnimatePresence mode="popLayout">
              {focusedSubtask && !notepadHidden && (
                <motion.div
                  key={focusedSubtask.id}
                  initial={{ opacity: 0, y: -12, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -12, scale: 0.97 }}
                  transition={{ type: 'spring', stiffness: 320, damping: 28 }}
                >
                  <SubtaskNotepad subtask={focusedSubtask} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          <AssessmentsPanel assessments={assessments} focusedTaskId={focusedTaskId} todayIso={todayIso} />
        </div>

        <div className="task-list-column">
          {isLoading && <p className="status-message">Loading...</p>}
          {error && (
            <p className="status-message error" role="alert">
              Failed to load tasks
            </p>
          )}

          <ProgressBar done={doneCount} total={mainTasks.length} />

          {mainTasks.length > 0 && (
            <p className="complete-hint">💡 Ctrl/Cmd+click a task to mark it complete</p>
          )}

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
                    focusedSubtaskId={focusedSubtaskId}
                    notepadHidden={notepadHidden}
                    onToggleNotepad={() => setNotepadHidden((h) => !h)}
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
                    focusedSubtaskId={focusedSubtaskId}
                    notepadHidden={notepadHidden}
                    onToggleNotepad={() => setNotepadHidden((h) => !h)}
                  />
                ))}
              </AnimatePresence>
            </ul>
          )}

          {filtered.length === 0 && <p className="status-message">No tasks match your filters yet.</p>}
        </div>
      </div>

      <KeyboardShortcutsHelp />
    </div>
  )
}
