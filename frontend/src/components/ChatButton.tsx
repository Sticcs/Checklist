import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useChatMessages, useMarkChatRead, useSendChatMessage } from '../hooks/useChat'

interface Props {
  taskId: number
  currentUsername?: string
}

// A round floating button (fixed to the workspace's bottom-right corner)
// with an unread badge, opening a small portaled chat panel - same button-
// ref/panel-ref/click-outside/portal-into-body structure as
// NotificationBell.tsx, just anchored to a fixed corner instead of an
// inline header icon, and its own poll (see useChatMessages) instead of
// that one's notifications poll.
export function ChatButton({ taskId, currentUsername }: Props) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const { data } = useChatMessages(taskId, open)
  const sendMessage = useSendChatMessage(taskId)
  const markRead = useMarkChatRead(taskId)

  const messages = data?.messages ?? []
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

  // Marks read the moment the panel opens - not on every background poll,
  // which would clear the badge before you'd actually seen anything.
  useEffect(() => {
    if (open) markRead.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (open) listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [open, messages.length])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const text = draft.trim()
    if (!text) return
    setDraft('')
    sendMessage.mutate(text)
  }

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
          <div ref={panelRef} className="assignment-chat-panel" data-focus-exempt>
            <div className="assignment-chat-panel-header">
              <p className="assessments-heading">💬 Chat</p>
              <button type="button" className="icon-btn" title="Close" onClick={() => setOpen(false)}>
                ✕
              </button>
            </div>
            <div ref={listRef} className="assignment-chat-messages">
              {messages.length === 0 && <p className="status-message">No messages yet.</p>}
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={m.username === currentUsername ? 'assignment-chat-message own' : 'assignment-chat-message'}
                >
                  <span className="assignment-chat-message-meta">
                    {m.username} · {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <span className="assignment-chat-message-text">{m.text}</span>
                </div>
              ))}
            </div>
            <form className="assignment-chat-form" onSubmit={submit}>
              <input
                placeholder="Message..."
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                maxLength={2000}
              />
              <button type="submit" className="btn-primary" disabled={draft.trim() === ''}>
                Send
              </button>
            </form>
          </div>,
          document.body
        )}
    </>
  )
}
