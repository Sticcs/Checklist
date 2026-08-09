import { useAuth } from './context/AuthContext'
import { AuthPage } from './pages/AuthPage'
import { TaskListPage } from './pages/TaskListPage'

export default function App() {
  const { status } = useAuth()

  if (status === 'loading') return null
  return status === 'authed' ? <TaskListPage /> : <AuthPage />
}
