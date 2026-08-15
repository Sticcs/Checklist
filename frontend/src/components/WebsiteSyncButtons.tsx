import { useState } from 'react'
import { useIsDesktopApp } from '../hooks/useIsDesktopApp'
import { useSyncFromWebsite, usePushToWebsite } from '../hooks/useData'

// Desktop app only - moves tasks between the currently logged-in local
// account and a website account, in either direction:
//   - Pull: website -> this local account (also happens automatically the
//     first time you log in locally with website credentials - see
//     backend/app/routers/auth.py's login()). This is the repeatable,
//     on-demand version, since the app never stores the website password to
//     re-run that check on its own.
//   - Push: this local account -> website. There's no way to build the
//     reverse of *this* (a "pull from the app" button on the website) - the
//     app's local server only exists at 127.0.0.1:<random-port> on this
//     machine while it's open, which the website's server has no route to.
//     Push covers the same need from the other end: an ordinary outbound
//     request the app itself initiates.
// Both share one credentials form since they're normally the same website
// account either way.
export function WebsiteSyncButtons() {
  const isDesktopApp = useIsDesktopApp()
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const pull = useSyncFromWebsite()
  const push = usePushToWebsite()

  if (!isDesktopApp) return null

  const pending = pull.isPending || push.isPending

  const handlePull = (e: React.FormEvent) => {
    e.preventDefault()
    pull.mutate(
      { username, password },
      {
        onSuccess: () => {
          setOpen(false)
          setPassword('')
        },
      }
    )
  }

  const handlePush = () => {
    push.mutate(
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
        title="Move tasks between this account and a website account"
      >
        🔄 Sync with website
      </button>
      {open && (
        <form className="sync-now-form" onSubmit={handlePull}>
          <input
            placeholder="Website username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={pending}
          />
          <input
            placeholder="Website password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={pending}
          />
          <div className="sync-now-actions">
            <button
              type="submit"
              className="btn-primary"
              disabled={pending}
              title="Pull this website account's tasks into this local account"
            >
              {pull.isPending ? 'Pulling...' : '⬇️ Pull'}
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={pending}
              onClick={handlePush}
              title="Push this local account's tasks up to the website"
            >
              {push.isPending ? 'Pushing...' : '⬆️ Push'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
