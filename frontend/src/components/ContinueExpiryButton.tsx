import { useEffect, useRef, useState } from 'react'
import type { ListEntry } from '../types'
import { useContinueExpiryList } from '../hooks/useLists'
import { toISODate } from '../utils/dueDatePresets'

interface Props {
  list: ListEntry
}

// Shown once an expiry checklist's countdown has actually hit zero (see
// ExpiryTimer, which renders this) - "Continue" re-runs the same
// choose-a-deadline step CreateListModal uses for a brand new expiry
// checklist, just against the existing list instead of creating a new one.
// Picking either option restarts the countdown and flags whatever's still
// incomplete as carried over (see useContinueExpiryList / TaskCard's
// carried-over styling).
export function ContinueExpiryButton({ list }: Props) {
  const continueList = useContinueExpiryList()
  const [menuOpen, setMenuOpen] = useState(false)
  const [customOpen, setCustomOpen] = useState(false)
  const [customValue, setCustomValue] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)

  // Same click-outside pattern as ListMenu's own popovers, including the
  // deferred-attachment fix for the same-tick-unmount race (the button
  // that opens this also sits inside the same click that would otherwise
  // close it instantly) - see ListMenu.tsx's matching comment.
  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    const id = window.setTimeout(() => document.addEventListener('click', handler), 0)
    return () => {
      window.clearTimeout(id)
      document.removeEventListener('click', handler)
    }
  }, [menuOpen])

  useEffect(() => {
    if (!customOpen) return
    const handler = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setCustomOpen(false)
    }
    const id = window.setTimeout(() => document.addEventListener('click', handler), 0)
    return () => {
      window.clearTimeout(id)
      document.removeEventListener('click', handler)
    }
  }, [customOpen])

  const continueWith = (expiresAt: string) => {
    continueList.mutate({ id: list.id, expiresAt })
    setMenuOpen(false)
    setCustomOpen(false)
  }

  // End of today, not "+24h" or "+1 calendar day then end of day" - the
  // latter landed as far as ~2 days out when pressed just after midnight
  // (tomorrow's 23:59 is nearly 48h away at that point). This matches
  // CreateListModal's own "by default it's the end of the day" default for
  // a brand new expiry checklist - "Another day" just re-applies that same
  // default to the existing list.
  const handleAnotherDay = () => {
    continueWith(`${toISODate(new Date())}T23:59`)
  }

  const openCustom = () => {
    setMenuOpen(false)
    setCustomValue(`${toISODate(new Date())}T23:59`)
    setCustomOpen(true)
  }

  return (
    <div className="continue-expiry" ref={rootRef} data-focus-exempt>
      <button
        type="button"
        className="btn-continue-expiry"
        onClick={(e) => {
          e.stopPropagation()
          setMenuOpen((open) => !open)
        }}
        disabled={continueList.isPending}
      >
        🔁 Continue
      </button>
      {menuOpen && (
        <div className="compact-menu-popover" data-focus-exempt>
          <button type="button" onClick={handleAnotherDay}>
            📅 Another day
          </button>
          <button type="button" onClick={openCustom}>
            🛠️ Custom
          </button>
        </div>
      )}
      {customOpen && (
        <div className="assignment-share-popover" data-focus-exempt>
          <input
            type="datetime-local"
            className="custom-input"
            value={customValue}
            onChange={(e) => setCustomValue(e.target.value)}
            autoFocus
          />
          <button
            type="button"
            className="btn-primary"
            disabled={!customValue}
            onClick={() => continueWith(customValue)}
          >
            Continue
          </button>
        </div>
      )}
    </div>
  )
}
