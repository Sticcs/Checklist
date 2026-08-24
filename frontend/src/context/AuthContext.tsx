import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { authApi } from '../api/auth'
import { resetUndoRedoStacks } from '../hooks/undoRedoStack'
import { markSaved } from '../hooks/saveState'
import { clearLinked } from '../hooks/websiteLink'
import type { User } from '../types'

type AuthStatus = 'loading' | 'authed' | 'anonymous'

interface AuthContextValue {
  status: AuthStatus
  user: User | null
  loginAsGuest: () => Promise<void>
  login: (username: string, password: string, rememberMe: boolean) => Promise<void>
  signup: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<User | null>(null)
  const queryClient = useQueryClient()

  useEffect(() => {
    authApi
      .me()
      .then((u) => {
        setUser(u)
        setStatus('authed')
      })
      .catch(() => setStatus('anonymous'))
  }, [])

  const settle = (u: User) => {
    setUser(u)
    setStatus('authed')
  }

  const loginAsGuest = async () => settle(await authApi.guest())
  const login = async (username: string, password: string, rememberMe: boolean) =>
    settle(await authApi.login(username, password, rememberMe))
  const signup = async (username: string, password: string) => {
    await authApi.signup(username, password)
  }
  const logout = async () => {
    await authApi.logout()
    setUser(null)
    setStatus('anonymous')
    // A fast re-login as a different user must never see the previous
    // user's cached tasks flash before the first refetch completes, or be
    // able to Undo/Redo into the previous user's history.
    queryClient.clear()
    resetUndoRedoStacks()
    markSaved()
    // Just resets this tab's own "linked" indicator so the next login (or a
    // brand-new guest) doesn't show a stale one before useWebsiteLinkStatus
    // re-fetches - the actual link this account has (if any) stays stored
    // server-side (crud.website_links) and reappears if they log back in.
    clearLinked()
  }

  return (
    <AuthContext.Provider value={{ status, user, loginAsGuest, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
