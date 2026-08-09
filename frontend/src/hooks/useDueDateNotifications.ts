import { useEffect } from 'react'
import type { Task } from '../types'
import { useSettings } from '../context/SettingsContext'
import { daysUntil, toISODate } from '../utils/dueDatePresets'

function notifiedKey(todayIso: string): string {
  return `checklist-notified:${todayIso}`
}

function loadNotified(todayIso: string): Set<string> {
  try {
    const raw = localStorage.getItem(notifiedKey(todayIso))
    return raw ? new Set(JSON.parse(raw)) : new Set()
  } catch {
    return new Set()
  }
}

function saveNotified(todayIso: string, ids: Set<string>) {
  localStorage.setItem(notifiedKey(todayIso), JSON.stringify([...ids]))
}

// Browser-notification reminder for anything due tomorrow. This only fires
// while the tab is open (no service worker / push infra behind it) - a
// deliberate scope limit, not an oversight, since a real push-based reminder
// system would need a server-side scheduler this app doesn't have.
export function useDueDateNotifications(tasks: Task[]) {
  const { notifyDayBefore } = useSettings()

  useEffect(() => {
    if (!notifyDayBefore) return
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return

    const todayIso = toISODate(new Date())
    const notified = loadNotified(todayIso)
    let changed = false

    const maybeNotify = (id: string, text: string, dueDate: string | null, done: boolean) => {
      if (done || !dueDate || notified.has(id)) return
      if (daysUntil(dueDate, todayIso) !== 1) return
      new Notification('Due tomorrow', { body: text })
      notified.add(id)
      changed = true
    }

    for (const task of tasks) {
      maybeNotify(`t${task.id}`, task.text, task.due_date, task.done)
      for (const subtask of task.subtasks) {
        maybeNotify(`s${subtask.id}`, subtask.text, subtask.due_date, subtask.done)
      }
    }

    if (changed) saveNotified(todayIso, notified)
  }, [tasks, notifyDayBefore])
}
