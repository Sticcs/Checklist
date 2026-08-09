import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { authApi } from '../api/auth'
import type { User } from '../types'

type AuthStatus = 'loading' | 'authed' | 'anonymous'

interface AuthContextValue {
  status: AuthStatus
  user: User | null
  loginAsGuest: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
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
  const login = async (username: string, password: string) => settle(await authApi.login(username, password))
  const signup = async (username: string, password: string) => {
    await authApi.signup(username, password)
  }
  const logout = async () => {
    await authApi.logout()
    setUser(null)
    setStatus('anonymous')
    // A fast re-login as a different user must never see the previous
    // user's cached tasks flash before the first refetch completes.
    queryClient.clear()
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
