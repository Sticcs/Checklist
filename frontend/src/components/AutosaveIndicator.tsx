import { useCallback, useEffect, useRef, useState } from 'react'
import { useIsDesktopApp } from '../hooks/useIsDesktopApp'
import { useLinkedCredentials } from '../hooks/websiteLink'
import { useIsDirty } from '../hooks/saveState'
import { usePushToWebsite } from '../hooks/useData'

const SAVE_INTERVAL_MS = 5 * 60 * 1000

function formatCountdown(ms: number): string {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000))
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

// Desktop app only, and only once a website account has been linked (via a
// successful Pull or Push - see WebsiteSyncButtons/websiteLink.ts): Push
// doubles as the app's save system from that point on, firing automatically
// every 5 minutes (if anything's actually changed - see saveState.ts) or
// immediately on Ctrl+S. This is purely the visible countdown; the same
// linked-credentials gate also drives the exit-save prompt (see
// ExitSavePrompt.tsx), which is what actually guarantees a save on the way
// out rather than just on a timer.
export function AutosaveIndicator() {
  const isDesktopApp = useIsDesktopApp()
  const linked = useLinkedCredentials()
  const dirty = useIsDirty()
  const push = usePushToWebsite()

  const linkedRef = useRef(linked)
  linkedRef.current = linked
  const dirtyRef = useRef(dirty)
  dirtyRef.current = dirty

  const deadlineRef = useRef(Date.now() + SAVE_INTERVAL_MS)
  const [remainingMs, setRemainingMs] = useState(SAVE_INTERVAL_MS)

  const save = useCallback(() => {
    const creds = linkedRef.current
    if (!creds) return
    push.mutate({ username: creds.username, password: creds.password })
    deadlineRef.current = Date.now() + SAVE_INTERVAL_MS
    setRemainingMs(SAVE_INTERVAL_MS)
  }, [push])

  // The 5-minute cycle: re-armed only when linking status changes, not on
  // every dirty/deadline change - dirtyRef/deadlineRef are read fresh inside
  // the tick instead, so the interval itself never needs to restart.
  useEffect(() => {
    if (!linked) return
    deadlineRef.current = Date.now() + SAVE_INTERVAL_MS
    setRemainingMs(SAVE_INTERVAL_MS)
    const id = setInterval(() => {
      const remaining = deadlineRef.current - Date.now()
      if (remaining > 0) {
        setRemainingMs(remaining)
        return
      }
      if (dirtyRef.current) {
        save()
      } else {
        deadlineRef.current = Date.now() + SAVE_INTERVAL_MS
        setRemainingMs(SAVE_INTERVAL_MS)
      }
    }, 1000)
    return () => clearInterval(id)
  }, [linked, save])

  useEffect(() => {
    if (!linked) return
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        save()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [linked, save])

  if (!isDesktopApp || !linked) return null

  return (
    <p className="autosave-indicator" title="Autosaves to the website every 5 minutes - or press Ctrl+S to save now">
      {push.isPending
        ? '💾 Saving…'
        : `💾 ${formatCountdown(remainingMs)} till save or press Ctrl+S`}
    </p>
  )
}
