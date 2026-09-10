import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './context/AuthContext.tsx'
import { ThemeProvider } from './context/ThemeContext.tsx'
import { SettingsProvider } from './context/SettingsContext.tsx'
import { FormattingProvider } from './context/FormattingContext.tsx'
import { PENDING_JOIN_TOKEN_KEY } from './constants'

// Captures a share link's token before React ever mounts. Google sign-in is
// a full-page redirect (see backend/app/routers/auth.py's google_callback,
// which always lands back on "/") - any in-memory storage of the token
// would be wiped by that navigation, so it has to survive in sessionStorage
// instead. Works identically whether the visitor ends up going through
// guest/username-password/Google, since this runs before any of them do.
// See TaskListPage's pending-join effect for where PENDING_JOIN_TOKEN_KEY is
// consumed, and useJoinAssignment for what actually happens with it.
const joinMatch = window.location.pathname.match(/^\/assignment\/join\/([^/]+)\/?$/)
if (joinMatch) {
  sessionStorage.setItem(PENDING_JOIN_TOKEN_KEY, joinMatch[1])
  window.history.replaceState(null, '', '/')
}

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <SettingsProvider>
          <AuthProvider>
            <FormattingProvider>
              <App />
              <Toaster position="bottom-right" richColors />
            </FormattingProvider>
          </AuthProvider>
        </SettingsProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
