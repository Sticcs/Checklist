export {}

// The JS side of backend/desktop.py's window.expose(...) call - only
// present inside the packaged desktop app (see useIsDesktopApp). Every
// exposed function returns a Promise, since the actual call crosses the
// JS<->Python bridge.
declare global {
  interface Window {
    pywebview?: {
      api?: {
        toggle_fullscreen?: () => Promise<void>
        save_export?: (filename: string, content: string) => Promise<boolean>
        notify?: (title: string, body: string) => Promise<void>
      }
    }
  }

  interface WindowEventMap {
    pywebviewready: Event
  }
}
