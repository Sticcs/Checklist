import { useRef } from 'react'
import { toast } from 'sonner'
import { useIsDesktopApp } from '../hooks/useIsDesktopApp'
import { useImportData } from '../hooks/useData'

// A plain <a href download> works fine in a real browser, but there's no
// browser download manager behind an embedded webview - WebView2/WKWebView
// either silently no-op the click or navigate to the raw JSON instead of
// saving it. Inside the desktop app, this goes through pywebview's own
// native save dialog instead (backend/desktop.py's save_export).
export function DataBackupButtons() {
  const isDesktopApp = useIsDesktopApp()
  const importFileInputRef = useRef<HTMLInputElement>(null)
  const importData = useImportData()

  const handleExportClick = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (!isDesktopApp) return
    e.preventDefault()
    try {
      const res = await fetch('/api/export')
      if (!res.ok) throw new Error('export request failed')
      const text = await res.text()
      const saved = await window.pywebview?.api?.save_export?.('checklist-export.json', text)
      if (saved) toast('💾 Exported')
      // saved === false just means the native save dialog was cancelled -
      // not an error, nothing to show for it.
    } catch {
      toast.error("Couldn't export - try again")
    }
  }

  const handleImportFile = async (file: File | undefined) => {
    if (!file) return
    try {
      const payload = JSON.parse(await file.text())
      importData.mutate(payload)
    } catch {
      toast.error("Couldn't read that file - make sure it's a Checklist export")
    }
  }

  return (
    <>
      <a
        className="btn-secondary btn-block"
        href="/api/export"
        download
        onClick={(e) => void handleExportClick(e)}
        title="Download every task, subtask, and note as a JSON file"
      >
        💾 Export data
      </a>
      <button
        type="button"
        className="btn-secondary btn-block"
        onClick={() => importFileInputRef.current?.click()}
        disabled={importData.isPending}
        title="Load tasks from a Checklist export file - adds to what's already here, doesn't replace it"
      >
        {importData.isPending ? 'Importing...' : '📤 Import data'}
      </button>
      <input
        ref={importFileInputRef}
        type="file"
        accept="application/json,.json"
        className="visually-hidden-input"
        onChange={(e) => {
          void handleImportFile(e.target.files?.[0])
          e.target.value = ''
        }}
      />
    </>
  )
}
