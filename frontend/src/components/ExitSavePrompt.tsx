import { useCallback, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useIsDesktopApp } from '../hooks/useIsDesktopApp'
import { useIsDirty } from '../hooks/saveState'
import { useLinked } from '../hooks/websiteLink'
import { useExitPromptVisible, showExitPrompt, hideExitPrompt } from '../hooks/exitPrompt'
import { usePushToWebsite } from '../hooks/useData'

// Desktop app only. backend/desktop.py intercepts the native window-close
// event and, if there's unsaved work linked to a website account, cancels
// the close and calls window.__checklistShowExitPrompt() instead, leaving
// it up to this modal (and close_app(), exposed back to Python) to actually
// finish closing - see desktop.py's on_closing/close_app for the other half
// of this. Python learns "is there unsaved work" from set_dirty_state(),
// pushed below whenever it changes, rather than asking the page for it on
// the way out - on_closing runs on the UI thread, and asking synchronously
// (evaluate_js) from there deadlocks WebView2 (see on_closing's comment).
export function ExitSavePrompt() {
  const isDesktopApp = useIsDesktopApp()
  const dirty = useIsDirty()
  const linked = useLinked()
  const visible = useExitPromptVisible()
  const push = usePushToWebsite()

  const saveAndExit = useCallback(() => {
    if (!linked) {
      hideExitPrompt()
      return
    }
    push.mutate(undefined, { onSuccess: () => void window.pywebview?.api?.close_app?.() })
  }, [push, linked])

  const exitWithoutSaving = useCallback(() => {
    hideExitPrompt()
    void window.pywebview?.api?.close_app?.()
  }, [])

  useEffect(() => {
    if (!isDesktopApp) return
    void window.pywebview?.api?.set_dirty_state?.(dirty, !!linked)
  }, [isDesktopApp, dirty, linked])

  useEffect(() => {
    if (!isDesktopApp) return
    window.__checklistShowExitPrompt = () => showExitPrompt()
    return () => {
      delete window.__checklistShowExitPrompt
    }
  }, [isDesktopApp])

  useEffect(() => {
    if (!visible) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        saveAndExit()
      } else if (e.key === 'Escape') {
        hideExitPrompt()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [visible, saveAndExit])

  if (!isDesktopApp) return null

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="shortcuts-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={() => hideExitPrompt()}
        >
          <motion.div
            className="shortcuts-modal exit-save-modal"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="shortcuts-modal-header">
              <h2>Save before exiting?</h2>
            </div>
            <p className="exit-save-message">
              You have unsaved changes. Press <kbd>Enter</kbd> to save and exit, or <kbd>Esc</kbd> to cancel.
            </p>
            <div className="exit-save-actions">
              <button type="button" className="btn-secondary" onClick={() => hideExitPrompt()}>
                Cancel
              </button>
              <button type="button" className="btn-primary" onClick={saveAndExit} disabled={push.isPending}>
                {push.isPending ? 'Saving…' : 'Save & Exit'}
              </button>
            </div>
            <button type="button" className="exit-save-discard" onClick={exitWithoutSaving}>
              Close without saving
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
