import { useEffect } from 'react'
import { isTypingElement } from '../utils/isTypingElement'
import { useUndo, useRedo } from './useUndoRedo'

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

// Escape exits whatever text box you're currently typing in - a plain
// blur, nothing more (it doesn't clear or discard what you typed). Applies
// app-wide (the quick-add input, subtask/list-item add boxes, notes/pages
// editors, inline edit forms, AddTaskForm's own custom-category/date
// fields inside its overlay) since it's driven by isTypingElement rather
// than any one component.
//
// The blur itself is deferred to a macrotask (setTimeout 0) rather than run
// synchronously inside this handler - this listener is registered at
// TaskListPage's mount, earlier than component-local Escape handlers that
// only attach once their own overlay opens (e.g. AddTaskForm's), and
// native bubble-phase listeners on the same event fire in registration
// order. Blurring synchronously here would change document.activeElement
// *before* those later handlers run their own isTypingElement check,
// making them see focus as already gone and fall through to whatever
// their "not typing" branch does (AddTaskForm's Escape branch cancels the
// whole overlay and wipes the typed text - exactly what this hook exists
// to avoid). queueMicrotask alone wasn't a long enough deferral in testing
// (something else - likely React's own scheduling - was still running a
// microtask in between the two listeners); setTimeout reliably lands after
// every same-tick handler has read the real focus state first.
export function useEscapeBlurHotkey() {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const active = document.activeElement
      if (!isTypingElement(active)) return
      window.setTimeout(() => (active as HTMLElement).blur(), 0)
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])
}

// Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y redoes - the standard
// desktop-app convention. Gated on isTypingElement so it doesn't hijack a
// text input's own native undo (e.g. reverting your last keystroke in the
// task-text or notes field) - the app-level hotkey only fires when focus
// isn't in a text field to begin with.
export function useUndoRedoHotkeys() {
  const undo = useUndo()
  const redo = useRedo()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      if (isTypingElement(document.activeElement)) return

      const key = e.key.toLowerCase()
      if (key === 'z' && e.shiftKey) {
        e.preventDefault()
        redo.mutate()
      } else if (key === 'z') {
        e.preventDefault()
        undo.mutate()
      } else if (key === 'y') {
        e.preventDefault()
        redo.mutate()
      }
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
