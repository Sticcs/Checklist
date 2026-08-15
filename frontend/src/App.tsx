import { AnimatePresence, motion } from 'framer-motion'
import { useAuth } from './context/AuthContext'
import { useDesktopFullscreenHotkey } from './hooks/useDesktopFullscreenHotkey'
import { AuthPage } from './pages/AuthPage'
import { TaskListPage } from './pages/TaskListPage'
import { ExitSavePrompt } from './components/ExitSavePrompt'

export default function App() {
  const { status } = useAuth()
  useDesktopFullscreenHotkey()

  if (status === 'loading') return null

  return (
    <>
      <ExitSavePrompt />
      <AnimatePresence mode="wait">
        {status === 'authed' ? (
          <motion.div
            key="app"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            <TaskListPage />
          </motion.div>
        ) : (
          <motion.div
            key="auth"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            <AuthPage />
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
