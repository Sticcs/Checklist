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
import { PublicListPage } from './pages/PublicListPage.tsx'
import { PENDING_JOIN_TOKEN_KEY } from './constants'

const root = createRoot(document.getElementById('root')!)

// A public, no-login shared list is a wholly different page, not a route
// within the normal app - no sidebar, no auth, no task entry, nothing else
// from <App/> at all (see PublicListPage's own comment). Checked first and
// rendered in place of the entire rest of this file when it matches, rather
// than being folded into the join-token bootstrap below, which only ever
// captures a token and continues booting the normal, authenticated app.
const listMatch = window.location.pathname.match(/^\/list\/([^/]+)\/?$/)
if (listMatch) {
  root.render(
    <StrictMode>
      <ThemeProvider>
        <PublicListPage token={listMatch[1]} />
        <Toaster position="bottom-right" richColors />
      </ThemeProvider>
    </StrictMode>,
  )
} else {
  // Captures a share link's token before React ever mounts. Google sign-in
  // is a full-page redirect (see backend/app/routers/auth.py's
  // google_callback, which always lands back on "/") - any in-memory
  // storage of the token would be wiped by that navigation, so it has to
  // survive in sessionStorage instead. Works identically whether the
  // visitor ends up going through guest/username-password/Google, since
  // this runs before any of them do. See TaskListPage's pending-join effect
  // for where PENDING_JOIN_TOKEN_KEY is consumed, and useJoinAssignment for
  // what actually happens with it.
  const joinMatch = window.location.pathname.match(/^\/assignment\/join\/([^/]+)\/?$/)
  if (joinMatch) {
    sessionStorage.setItem(PENDING_JOIN_TOKEN_KEY, joinMatch[1])
    window.history.replaceState(null, '', '/')
  }

  const queryClient = new QueryClient()

  root.render(
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
}
