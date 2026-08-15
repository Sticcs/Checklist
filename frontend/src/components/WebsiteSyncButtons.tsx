import { useState } from 'react'
import { useIsDesktopApp } from '../hooks/useIsDesktopApp'
import { useSyncFromWebsite, usePushToWebsite, useUnlinkWebsite } from '../hooks/useData'
import { useLinked } from '../hooks/websiteLink'

// Desktop app only - mirrors tasks between the currently logged-in local
// account and a website account, in either direction:
//   - Pull: website -> this local account, replacing it (see
//     crud.import_data's replace mode) - also happens automatically the
//     first time you log in locally with website credentials (see
//     backend/app/routers/auth.py's login()). This is the repeatable,
//     on-demand version.
//   - Push: this local account -> website, replacing it. There's no way to
//     build the reverse of *this* (a "pull from the app" button on the
//     website) - the app's local server only exists at
//     127.0.0.1:<random-port> on this machine while it's open, which the
//     website's server has no route to. Push covers the same need from the
//     other end: an ordinary outbound request the app itself initiates.
// Both share one credentials form since they're normally the same website
// account either way. Whichever succeeds first links the account - the
// backend remembers those credentials itself (crud.set_website_link), so it
// stays linked across app restarts until this local account links a
// different one (overwriting it) or explicitly unlinks. Being linked is
// what turns on the autosave timer/Ctrl+S/exit-save-prompt
// (AutosaveIndicator.tsx, ExitSavePrompt.tsx) - Push effectively becomes
// the app's save system from that point on.
export function WebsiteSyncButtons() {
  const isDesktopApp = useIsDesktopApp()
  const linked = useLinked()
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const pull = useSyncFromWebsite()
  const push = usePushToWebsite()
  const unlink = useUnlinkWebsite()

  if (!isDesktopApp) return null

  const pending = pull.isPending || push.isPending || unlink.isPending

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
        {linked ? `🔄 Linked to ${linked}` : '🔄 Sync with website'}
      </button>
      {open && (
        <div className="sync-now-panel">
          {linked && (
            <div className="sync-now-linked-row">
              <span>Currently linked to “{linked}”. Link a different account below, or:</span>
              <button type="button" className="sync-now-unlink" disabled={pending} onClick={() => unlink.mutate()}>
                Unlink
              </button>
            </div>
          )}
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
                title="Replace this local account's tasks with the website's"
              >
                {pull.isPending ? 'Pulling...' : '⬇️ Pull'}
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={pending}
                onClick={handlePush}
                title="Replace the website's tasks with this local account's"
              >
                {push.isPending ? 'Pushing...' : '⬆️ Push'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
