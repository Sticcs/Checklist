import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { publicApi } from '../api/public'
import type { PublicListItem } from '../types'

interface Props {
  token: string
}

// The entire public, no-login surface for a shared list - no sidebar, no
// task entry, no sign-in prompt, nothing else from the rest of the app.
// Rendered by main.tsx in place of the normal <App/> tree entirely when the
// URL matches /list/<token>, so there's no app shell to strip away here -
// this component genuinely is the whole page.
export function PublicListPage({ token }: Props) {
  const [listName, setListName] = useState<string | null>(null)
  const [items, setItems] = useState<PublicListItem[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    publicApi
      .getList(token)
      .then((res) => {
        if (cancelled) return
        setListName(res.list_name)
        setItems(res.items)
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const toggleItem = (item: PublicListItem) => {
    const nextDone = !item.done
    // Optimistic - this page has no undo/redo, no session, nothing to
    // reconcile beyond the list itself, so a plain local update plus a
    // rollback on failure is all that's needed.
    setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, done: nextDone } : i)))
    publicApi.setItemDone(token, item.id, nextDone).catch(() => {
      setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, done: item.done } : i)))
    })
  }

  return (
    <div className="public-list-page">
      <div className="public-list-card">
        {status === 'loading' && <p className="status-message">Loading…</p>}
        {status === 'error' && (
          <p className="status-message error" role="alert">
            This link is invalid or has been revoked.
          </p>
        )}
        {status === 'ready' && (
          <>
            <h1 className="public-list-title">{listName}</h1>
            <ul className="shopping-list">
              <AnimatePresence>
                {items.map((item) => (
                  <motion.li
                    key={item.id}
                    layout
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, ease: 'easeOut' }}
                    className={item.done ? 'shopping-item done' : 'shopping-item'}
                  >
                    <input
                      type="checkbox"
                      className="task-done-checkbox"
                      checked={item.done}
                      onChange={() => toggleItem(item)}
                    />
                    <span className={item.done ? 'task-text done' : 'task-text'}>{item.text}</span>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
            {items.length === 0 && <p className="status-message">This list is empty.</p>}
          </>
        )}
      </div>
    </div>
  )
}
