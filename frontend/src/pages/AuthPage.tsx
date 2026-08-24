import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useIsDesktopApp } from '../hooks/useIsDesktopApp'
import { ApiError } from '../api/client'
import { AuthQuotes } from '../components/AuthQuotes'
import { DownloadAppButton } from '../components/DownloadAppButton'
import { PRODUCTION_URL } from '../constants'

export function AuthPage() {
  const { loginAsGuest, login, signup } = useAuth()
  const isDesktopApp = useIsDesktopApp()
  // OAuth is a full-page-redirect flow, not a fetch call - and from inside
  // the desktop app it must hit the real deployed backend directly (an
  // absolute URL, leaving the local server's page entirely), never the
  // local-only server the rest of the app talks to. See PRODUCTION_URL.
  const googleLoginHref = isDesktopApp
    ? `${PRODUCTION_URL}/api/auth/google/login`
    : '/api/auth/google/login'
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [signupDone, setSignupDone] = useState(false)
  // Credentials genuinely have to be verified server-side before showing the
  // app - there's no honest way to "optimistically" log someone in. What was
  // actually making this feel slow was the button sitting inert with no
  // feedback during that wait, so the fix here is immediate pending state
  // (disabled + relabeled) the instant the click registers, not skipping
  // the verification itself.
  const [submitting, setSubmitting] = useState<'login' | 'signup' | 'guest' | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(mode)
    try {
      if (mode === 'login') {
        await login(username, password, rememberMe)
      } else {
        await signup(username, password)
        setSignupDone(true)
        setMode('login')
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    } finally {
      setSubmitting(null)
    }
  }

  const handleGuest = async () => {
    setError(null)
    setSubmitting('guest')
    try {
      await loginAsGuest()
    } catch {
      setError('Something went wrong')
      setSubmitting(null)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-stack">
        <AuthQuotes />
        <div className="auth-card">
          <h1 className="auth-title">✅ My Checklist</h1>

          {isDesktopApp && (
            <p className="desktop-app-note">
              🖥️ App version - local accounts keep separate data from the website (import it via the sidebar), or
              sign in with Google for the same account and tasks online (needs internet).
            </p>
          )}

          <div className="auth-tabs">
            <button
              type="button"
              className={mode === 'login' ? 'auth-tab active' : 'auth-tab'}
              onClick={() => setMode('login')}
            >
              Login
            </button>
            <button
              type="button"
              className={mode === 'signup' ? 'auth-tab active' : 'auth-tab'}
              onClick={() => setMode('signup')}
            >
              Sign Up
            </button>
          </div>

          {signupDone && <p className="auth-success">Account created! You can now log in.</p>}

          <form className="auth-form" onSubmit={handleSubmit}>
            <input
              placeholder={mode === 'login' ? 'Enter your username' : 'Pick a username'}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={submitting !== null}
            />
            <input
              placeholder={mode === 'login' ? 'Enter your password' : 'Pick a password'}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting !== null}
            />
            {mode === 'login' && (
              <label className="checkbox-label auth-remember-label">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  disabled={submitting !== null}
                />
                Keep me logged in for 30 days
              </label>
            )}
            <button type="submit" className="btn-primary btn-block" disabled={submitting !== null}>
              {mode === 'login'
                ? submitting === 'login'
                  ? 'Logging in...'
                  : 'Login'
                : submitting === 'signup'
                  ? 'Creating account...'
                  : 'Create Account'}
            </button>
          </form>

          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}

          <hr />

          <a href={googleLoginHref} className="btn-secondary btn-block google-signin-btn">
            Sign in with Google
          </a>

          <button
            type="button"
            className="btn-secondary btn-block"
            onClick={handleGuest}
            disabled={submitting !== null}
          >
            {submitting === 'guest' ? 'Continuing...' : 'Continue as Guest'}
          </button>
        </div>
      </div>
      <DownloadAppButton variant="floating" />
    </div>
  )
}
