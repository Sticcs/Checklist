import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNotifications, useMarkNotificationRead, useMarkAllNotificationsRead } from '../hooks/useNotifications'
import { useTasks } from '../hooks/useTasks'
import { useSharedWithMe } from '../hooks/useCollaboration'
import { getDueTomorrowEntries } from '../utils/dueTomorrow'
import type { NotificationEntry } from '../types'

interface Props {
  // Opens the AssignmentWorkspace for this task id (see TaskListPage's
  // setActiveAssignmentId) - every notification kind that carries a task_id
  // is assignment-related (item_checked/subtask_assigned only ever fire on
  // Assessment-category tasks - see the backend trigger points), so this is
  // always the right thing to do when one is present.
  onOpenTask: (taskId: number) => void
}

const KIND_ICON: Record<string, string> = {
  item_checked: '✅',
  subtask_assigned: '🎯',
  access_revoked: '🚫',
}

export function NotificationBell({ onOpenTask }: Props) {
  const [open, setOpen] = useState(false)
  const [panelPos, setPanelPos] = useState({ top: 0, left: 0 })
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const { data } = useNotifications()
  const { data: tasksData } = useTasks()
  const { data: sharedTasks } = useSharedWithMe()
  const markRead = useMarkNotificationRead()
  const markAllRead = useMarkAllNotificationsRead()

  const dueTomorrow = useMemo(
    () => [...getDueTomorrowEntries(tasksData?.tasks ?? []), ...getDueTomorrowEntries(sharedTasks ?? [])],
    [tasksData, sharedTasks]
  )

  const notifications = data?.notifications ?? []
  const unreadCount = (data?.unread_count ?? 0) + dueTomorrow.length

  const toggleOpen = () => {
    if (!open && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect()
      setPanelPos({ top: rect.bottom + 6, left: rect.left })
    }
    setOpen((v) => !v)
  }

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (!buttonRef.current?.contains(target) && !panelRef.current?.contains(target)) setOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [open])

  const handleEntryClick = (entry: NotificationEntry) => {
    if (!entry.read) markRead.mutate(entry.id)
    if (entry.task_id !== null) {
      onOpenTask(entry.task_id)
      setOpen(false)
    }
  }

  const openTaskAndClose = (taskId: number) => {
    onOpenTask(taskId)
    setOpen(false)
  }

  return (
    <div className="notification-bell" data-focus-exempt>
      <button
        ref={buttonRef}
        type="button"
        className="icon-btn"
        aria-expanded={open}
        title="Notifications"
        onClick={toggleOpen}
      >
        🔔
        {unreadCount > 0 && <span className="notification-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>}
      </button>

      {open &&
        createPortal(
          // Portaled straight into <body> (same pattern as AddTaskForm's
          // TaskEntryVignetteOverlay) - .sidebar-wrapper's own overflow:
          // hidden (needed for its width-collapse animation) would otherwise
          // clip this panel instead of letting it float over the page.
          <div
            ref={panelRef}
            className="notification-panel"
            style={{ top: panelPos.top, left: panelPos.left }}
            data-focus-exempt
          >
            {dueTomorrow.length > 0 && (
              <div className="notification-section">
                <p className="notification-section-title">Due tomorrow</p>
                {dueTomorrow.map((entry) => (
                  <button
                    key={entry.id}
                    type="button"
                    className="notification-entry"
                    onClick={() => openTaskAndClose(entry.taskId)}
                  >
                    <span className="notification-entry-icon">⏰</span>
                    <span className="notification-entry-text">{entry.text}</span>
                  </button>
                ))}
              </div>
            )}

            <div className="notification-section">
              <div className="notification-section-header">
                <p className="notification-section-title">Notifications</p>
                {notifications.some((n) => !n.read) && (
                  <button type="button" className="notification-mark-all" onClick={() => markAllRead.mutate()}>
                    Mark all read
                  </button>
                )}
              </div>
              {notifications.length === 0 && <p className="status-message">No notifications yet.</p>}
              {notifications.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  className={entry.read ? 'notification-entry' : 'notification-entry unread'}
                  onClick={() => handleEntryClick(entry)}
                >
                  <span className="notification-entry-icon">{KIND_ICON[entry.kind] ?? '•'}</span>
                  <span className="notification-entry-body">
                    <span className="notification-entry-text">{entry.message}</span>
                    <span className="notification-entry-time">{new Date(entry.created_at).toLocaleString()}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>,
          document.body
        )}
    </div>
  )
}
