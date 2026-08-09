import { useEffect } from 'react'
import { isTypingElement } from '../utils/isTypingElement'

interface Params {
  latestTaskId: number | null
  lastExpandedTaskId: number | null
  onConsumeLatest: () => void
}

// '/' focuses the most-recently-added task's subtask input, falling back to
// whichever panel was last expanded by hand once the "just added" hint is
// consumed - matches the priority order from the Streamlit version.
export function useSubtaskFocusHotkey({ latestTaskId, lastExpandedTaskId, onConsumeLatest }: Params) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== '/') return
      if (isTypingElement(document.activeElement)) return

      const targetId = latestTaskId ?? lastExpandedTaskId
      if (targetId === null) return
      e.preventDefault()

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

      if (latestTaskId !== null) onConsumeLatest()
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [latestTaskId, lastExpandedTaskId, onConsumeLatest])
}
