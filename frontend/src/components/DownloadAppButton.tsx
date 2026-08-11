import { useIsDesktopApp } from '../hooks/useIsDesktopApp'

interface Props {
  variant?: 'sidebar' | 'floating'
}

type Platform = 'mac' | 'windows'

const DOWNLOADS: Record<Platform, { href: string; label: string; hint: string }> = {
  mac: {
    href: '/downloads/ChecklistApp-mac.zip',
    label: 'Mac',
    hint: 'Downloads a .zip containing the app - same app, runs as a native window',
  },
  windows: {
    href: '/downloads/ChecklistApp.exe',
    label: 'Windows',
    hint: 'Downloads a standalone .exe - same app, runs as a native window',
  },
}

// Best-effort OS sniff so the button offers the right download by default -
// wrong on an OS this app doesn't ship for (Linux, mobile), which is exactly
// why the sidebar variant still surfaces the other platform's link rather
// than committing to only one guess.
function detectPlatform(): Platform {
  if (typeof navigator === 'undefined') return 'windows'
  const platform = navigator.platform || navigator.userAgent || ''
  return /mac/i.test(platform) ? 'mac' : 'windows'
}

// Hidden automatically when the site is already running inside the packaged
// desktop app itself (see useIsDesktopApp) - offering to download it again
// there would be pointless.
export function DownloadAppButton({ variant = 'sidebar' }: Props) {
  const isDesktopApp = useIsDesktopApp()
  if (isDesktopApp) return null

  const primary = detectPlatform()
  const other: Platform = primary === 'mac' ? 'windows' : 'mac'

  if (variant === 'floating') {
    return (
      <a
        className="download-app-floating-btn"
        href={DOWNLOADS[primary].href}
        download
        title={DOWNLOADS[primary].hint}
      >
        ⬇️ Get the app
      </a>
    )
  }

  return (
    <div className="download-app-group">
      <a
        className="btn-secondary btn-block download-app-btn"
        href={DOWNLOADS[primary].href}
        download
        title={DOWNLOADS[primary].hint}
      >
        ⬇️ Download app ({DOWNLOADS[primary].label})
      </a>
      <a className="download-app-alt-link" href={DOWNLOADS[other].href} download title={DOWNLOADS[other].hint}>
        Download for {DOWNLOADS[other].label} instead
      </a>
    </div>
  )
}
