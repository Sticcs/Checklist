import { useEffect } from 'react'
import type { Task } from '../types'
import { useSettings } from '../context/SettingsContext'
import { useIsDesktopApp } from './useIsDesktopApp'
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

// A reminder for anything due tomorrow. This only fires while the app is
// open (no service worker / push infra behind it) - a deliberate scope
// limit, not an oversight, since a real push-based reminder system would
// need a server-side scheduler this app doesn't have.
export function useDueDateNotifications(tasks: Task[]) {
  const { notifyDayBefore } = useSettings()
  const isDesktopApp = useIsDesktopApp()

  useEffect(() => {
    if (!notifyDayBefore) return
    // The desktop app's native notify() (backend/desktop.py, via plyer)
    // needs no permission grant - the Web Notification API the website
    // falls back to does, and isn't reliably available inside an embedded
    // webview at all (WKWebView in particular has no permission UI for it).
    if (!isDesktopApp && (typeof Notification === 'undefined' || Notification.permission !== 'granted')) return

    const todayIso = toISODate(new Date())
    const notified = loadNotified(todayIso)
    let changed = false

    const maybeNotify = (id: string, text: string, dueDate: string | null, done: boolean) => {
      if (done || !dueDate || notified.has(id)) return
      if (daysUntil(dueDate, todayIso) !== 1) return
      if (isDesktopApp) {
        void window.pywebview?.api?.notify?.('Due tomorrow', text)
      } else {
        new Notification('Due tomorrow', { body: text })
      }
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
  }, [tasks, notifyDayBefore, isDesktopApp])
}
