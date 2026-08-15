import type { CapacitorConfig } from '@capacitor/cli'

// The app doesn't bundle a local copy of the frontend and talk cross-origin
// to the API the way a typical Capacitor app would - it points server.url
// straight at the live deployment instead, so the native shell just displays
// the real site. That sidesteps two real problems a bundled-assets setup
// would create: the backend has no CORS config today (it's only ever served
// same-origin, to the website itself or to the desktop app's own local
// server - see backend/desktop.py), and the auth cookie is SameSite=Lax,
// which flatly doesn't get sent cross-origin at all. Loading the real origin
// directly means cookies, routing, and every API call behave exactly like
// the website - and any future web deploy shows up in the app immediately,
// no rebuild needed. Trade-off: the app requires an internet connection,
// same as "Sign in with Google" already does on the desktop build.
const config: CapacitorConfig = {
  appId: 'com.debayanm.checklist',
  appName: 'Checklist',
  webDir: 'dist',
  server: {
    url: 'https://checklist-kmtw.onrender.com',
    cleartext: false,
  },
  ios: {
    contentInset: 'automatic',
  },
}

export default config
