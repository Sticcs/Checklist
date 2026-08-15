import { useState } from 'react'
import { useIsDesktopApp } from '../hooks/useIsDesktopApp'
import { useSyncFromWebsite } from '../hooks/useData'

// Desktop app only - pulls a website account's tasks into whichever local
// account is currently logged in. The one-time version of this happens
// automatically the first time you log in locally with website credentials
// (see backend/app/routers/auth.py's login()); this is the repeatable,
// on-demand version, since the app never stores the website password to
// re-run that check on its own.
export function SyncNowButton() {
  const isDesktopApp = useIsDesktopApp()
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const sync = useSyncFromWebsite()

  if (!isDesktopApp) return null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    sync.mutate(
      { username, password },
      {
        onSuccess: () => {
          setOpen(false)
          setPassword('')
        },
      }
    )
  }

  return (
    <div className="sync-now">
      <button
        type="button"
        className="btn-secondary btn-block"
        onClick={() => setOpen((v) => !v)}
        title="Pull your tasks from the website into this account"
      >
        {sync.isPending ? 'Syncing...' : '🔄 Sync now'}
      </button>
      {open && (
        <form className="sync-now-form" onSubmit={handleSubmit}>
          <input
            placeholder="Website username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={sync.isPending}
          />
          <input
            placeholder="Website password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={sync.isPending}
          />
          <button type="submit" className="btn-primary btn-block" disabled={sync.isPending}>
            {sync.isPending ? 'Syncing...' : 'Pull my data'}
          </button>
        </form>
      )}
    </div>
  )
}
