import { useEffect, useState } from 'react'
import type { ListEntry } from '../types'
import { useClearCompletedInList } from '../hooks/useLists'
import { useTasks } from '../hooks/useTasks'
import { expiryGlowClass, expiryProgressMessage, expiryRemainingMs, formatRemaining } from '../utils/listExpiry'
import { ContinueExpiryButton } from './ContinueExpiryButton'

interface Props {
  list: ListEntry
}

// A live, actively-ticking countdown for an expiry list's panel - separate
// from TaskListPage's own slower (30s) "now" tick, which only drives the
// glow border/tab and doesn't need second-level precision. Owning its own
// 1s interval here, in a small leaf component, means only this piece of
// the page re-renders every second, not the whole task list.
//
// Also owns the "ran out of time" moment itself: once expired, any
// completed task in this list gets swept (see useClearCompletedInList) and
// the "Continue" button appears. The sweep isn't a one-shot "fire once the
// instant it crosses zero" effect - it reacts to hasDoneTasks instead, so a
// task finished *after* it already expired (but before Continue is
// pressed) still gets cleared immediately rather than lingering until the
// next cycle. Once cleared, hasDoneTasks goes false and the effect goes
// quiet again - no polling, no repeated calls.
export function ExpiryTimer({ list }: Props) {
  const [now, setNow] = useState(() => Date.now())
  const clearCompletedInList = useClearCompletedInList()
  const { data: tasksData } = useTasks()

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const remaining = expiryRemainingMs(list, now)
  const expired = remaining !== null && remaining <= 0
  const hasDoneTasks = (tasksData?.tasks ?? []).some((t) => t.list_id === list.id && t.done)

  useEffect(() => {
    if (!expired || !hasDoneTasks) return
    clearCompletedInList.mutate(list.id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expired, hasDoneTasks, list.id])

  if (remaining === null) return null
  const glowClass = expiryGlowClass(list, now)
  const message = expiryProgressMessage(list, now)

  return (
    <div className="expiry-timer-row">
      <div className={`expiry-timer ${glowClass}`.trim()}>
        <span className="expiry-timer-countdown">{expired ? 'Overdue' : formatRemaining(remaining)}</span>
        <span className="expiry-timer-message">{message}</span>
      </div>
      {expired && <ContinueExpiryButton list={list} />}
    </div>
  )
}
