import { useEffect } from 'react'
import { useIsDesktopApp } from './useIsDesktopApp'

declare global {
  interface Window {
    pywebview?: {
      api?: {
        toggle_fullscreen?: () => void
      }
    }
  }
}

// A native pywebview window has no browser chrome to supply F11 fullscreen
// the way a real browser tab does - backend/desktop.py exposes a
// toggle_fullscreen() JS API for exactly this. No-ops outside the desktop
// app, where the browser already owns F11 on its own.
export function useDesktopFullscreenHotkey() {
  const isDesktopApp = useIsDesktopApp()

  useEffect(() => {
    if (!isDesktopApp) return

    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'F11') return
      e.preventDefault()
      window.pywebview?.api?.toggle_fullscreen?.()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isDesktopApp])
}
