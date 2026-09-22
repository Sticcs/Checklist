import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useChatMessages } from '../hooks/useChat'
import { ChatPanel } from './ChatPanel'

interface Props {
  taskId: number
  currentUsername?: string
}

// A round floating button (fixed to the workspace's bottom-right corner)
// with an unread badge, opening ChatPanel - same button-ref/panel-ref/
// click-outside/portal-into-body structure as NotificationBell.tsx, just
// anchored to a fixed corner instead of an inline header icon.
export function ChatButton({ taskId, currentUsername }: Props) {
  const [open, setOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // Polls even while closed (see useChatMessages) purely so the badge
  // count stays current - the panel itself only mounts while open.
  const { data } = useChatMessages(taskId, open)
  const unreadCount = data?.unread_count ?? 0

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (!buttonRef.current?.contains(target) && !panelRef.current?.contains(target)) setOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [open])

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="assignment-chat-btn"
        title="Chat"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((prev) => !prev)
        }}
      >
        💬
        {unreadCount > 0 && <span className="notification-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>}
      </button>

      {open &&
        createPortal(
          <ChatPanel ref={panelRef} taskId={taskId} currentUsername={currentUsername} onClose={() => setOpen(false)} />,
          document.body
        )}
    </>
  )
}
