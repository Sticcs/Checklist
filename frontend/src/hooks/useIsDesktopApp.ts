import { useEffect, useState } from 'react'

// pywebview injects `window.pywebview` into the page it's showing - true
// only when this site is already running inside the packaged desktop app
// itself (see backend/desktop.py), where offering to download it again
// would be pointless. Its window may not have finished injecting it by
// first render, hence also listening for its ready event.
export function useIsDesktopApp(): boolean {
  const [isDesktopApp, setIsDesktopApp] = useState(
    () => typeof window !== 'undefined' && 'pywebview' in window
  )

  useEffect(() => {
    if (isDesktopApp) return
    const handler = () => setIsDesktopApp(true)
    window.addEventListener('pywebviewready', handler)
    return () => window.removeEventListener('pywebviewready', handler)
  }, [isDesktopApp])

  return isDesktopApp
}
