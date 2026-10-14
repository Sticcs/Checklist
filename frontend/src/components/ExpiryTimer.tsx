import { useEffect, useState } from 'react'
import type { ListEntry } from '../types'
import { expiryGlowClass, expiryProgressMessage, expiryRemainingMs, formatRemaining } from '../utils/listExpiry'

interface Props {
  list: ListEntry
}

// A live, actively-ticking countdown for an expiry list's panel - separate
// from TaskListPage's own slower (30s) "now" tick, which only drives the
// glow border/tab and doesn't need second-level precision. Owning its own
// 1s interval here, in a small leaf component, means only this piece of
// the page re-renders every second, not the whole task list.
export function ExpiryTimer({ list }: Props) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const remaining = expiryRemainingMs(list, now)
  if (remaining === null) return null
  const glowClass = expiryGlowClass(list, now)
  const message = expiryProgressMessage(list, now)

  return (
    <div className={`expiry-timer ${glowClass}`.trim()}>
      <span className="expiry-timer-countdown">{remaining <= 0 ? 'Overdue' : formatRemaining(remaining)}</span>
      <span className="expiry-timer-message">{message}</span>
    </div>
  )
}
