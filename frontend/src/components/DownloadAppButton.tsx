import { useIsDesktopApp } from '../hooks/useIsDesktopApp'

interface Props {
  variant?: 'sidebar' | 'floating'
}

// Hidden automatically when the site is already running inside the
// packaged desktop app itself (see useIsDesktopApp) - offering to download
// it again there would be pointless.
export function DownloadAppButton({ variant = 'sidebar' }: Props) {
  const isDesktopApp = useIsDesktopApp()
  if (isDesktopApp) return null

  const className =
    variant === 'floating' ? 'download-app-floating-btn' : 'btn-secondary btn-block download-app-btn'

  return (
    <a
      className={className}
      href="/downloads/Checklist-Windows.exe"
      download
      title="Downloads a standalone .exe - same app, runs as a native window"
    >
      {variant === 'floating' ? '⬇️ Get the app' : '⬇️ Download app (Windows)'}
    </a>
  )
}
