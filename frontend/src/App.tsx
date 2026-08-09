import { AnimatePresence, motion } from 'framer-motion'
import { useAuth } from './context/AuthContext'
import { AuthPage } from './pages/AuthPage'
import { TaskListPage } from './pages/TaskListPage'

export default function App() {
  const { status } = useAuth()

  if (status === 'loading') return null

  return (
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
  )
}
