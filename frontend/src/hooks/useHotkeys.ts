import { useEffect } from 'react'
import { isTypingElement } from '../utils/isTypingElement'

interface Params {
  focusedTaskId: number | null
  latestTaskId: number | null
  lastExpandedTaskId: number | null
  onConsumeLatest: () => void
}

// '/' targets, in priority order: the task currently focused by a plain
// click, then the most-recently-added task, then whichever panel was last
// expanded by hand - and opens/focuses ITS subtask input. With no task in
// any of those states, it focuses the main task-entry input instead, so '/'
// always does something useful from anywhere on the page.
export function useSubtaskFocusHotkey({ focusedTaskId, latestTaskId, lastExpandedTaskId, onConsumeLatest }: Params) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== '/') return
      if (isTypingElement(document.activeElement)) return
      e.preventDefault()

      const targetId = focusedTaskId ?? latestTaskId ?? lastExpandedTaskId
      if (targetId === null) {
        const mainInput = document.querySelector('.task-text-input') as HTMLInputElement | null
        mainInput?.focus()
        return
      }

      const focusInput = () => {
        const input = document.getElementById(`subtask-input-${targetId}`) as HTMLInputElement | null
        input?.focus()
      }

      const input = document.getElementById(`subtask-input-${targetId}`)
      if (input) {
        focusInput()
      } else {
        // Panel isn't open yet - click its toggle button, then focus once
        // the input has had a render to appear.
        const card = document.querySelector(`[data-task-id="${targetId}"]`)
        const toggleBtn = card
          ? Array.from(card.querySelectorAll('button')).find((b) =>
              b.textContent?.toLowerCase().includes('subtask')
            )
          : null
        toggleBtn?.click()
        setTimeout(focusInput, 50)
      }

      if (focusedTaskId === null && latestTaskId !== null) onConsumeLatest()
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [focusedTaskId, latestTaskId, lastExpandedTaskId, onConsumeLatest])
}
