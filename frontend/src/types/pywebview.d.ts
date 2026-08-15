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
        close_app?: () => Promise<void>
        // Pushed to Python proactively (see ExitSavePrompt.tsx) rather than
        // pulled - backend/desktop.py's window.events.closing handler reads
        // this synchronously off a plain Python-side variable, since calling
        // evaluate_js from inside that handler deadlocks WebView2 (see its
        // on_closing comment for why).
        set_dirty_state?: (dirty: boolean, linked: boolean) => Promise<void>
      }
    }
    // Called by backend/desktop.py's on_closing, off a background thread,
    // once it's decided (from the pushed state above) that this needs to be
    // shown - see ExitSavePrompt.tsx for where this gets assigned.
    __checklistShowExitPrompt?: () => void
  }

  interface WindowEventMap {
    pywebviewready: Event
  }
}
