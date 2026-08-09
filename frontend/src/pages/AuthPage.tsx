import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../api/client'

export function AuthPage() {
  const { loginAsGuest, login, signup } = useAuth()
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
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
        await login(username, password)
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
      <div className="auth-card">
        <h1 className="auth-title">✅ My Checklist</h1>

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
  )
}
