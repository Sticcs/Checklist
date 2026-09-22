import { forwardRef, useEffect, useRef, useState } from 'react'
import { useChatMessages, useMarkChatRead, useSendChatMessage } from '../hooks/useChat'

interface Props {
  taskId: number
  currentUsername?: string
  onClose: () => void
  // Shown in the header next to the close button - lets a caller that
  // opens this for a specific assignment (see ChatLauncher's conversation
  // list, outside any one assignment's own workspace) show which one this
  // is, since "💬 Chat" alone wouldn't say.
  title?: string
}

// The floating chat panel's actual content, extracted so it can be opened
// two ways: ChatButton (mounted inside AssignmentWorkspace, always this
// one assignment) and ChatLauncher (the main screen's conversation-list
// launcher, which opens this for whichever assignment you pick). The
// trigger button + click-outside-closes logic stays in each caller (same
// shape as NotificationBell's own button/panel split), just sharing this
// one panel body instead of duplicating it.
export const ChatPanel = forwardRef<HTMLDivElement, Props>(function ChatPanel(
  { taskId, currentUsername, onClose, title },
  ref
) {
  const [draft, setDraft] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  const { data } = useChatMessages(taskId, true)
  const sendMessage = useSendChatMessage(taskId)
  const markRead = useMarkChatRead(taskId)

  const messages = data?.messages ?? []

  // Marks read once, the moment this panel mounts for this taskId - not on
  // every background poll, which would clear the badge before you'd
  // actually seen anything.
  useEffect(() => {
    markRead.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages.length])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const text = draft.trim()
    if (!text) return
    setDraft('')
    sendMessage.mutate(text)
  }

  return (
    <div ref={ref} className="assignment-chat-panel" data-focus-exempt>
      <div className="assignment-chat-panel-header">
        <p className="assessments-heading">💬 {title ?? 'Chat'}</p>
        <button type="button" className="icon-btn" title="Close" onClick={onClose}>
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
        <input placeholder="Message..." value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={2000} />
        <button type="submit" className="btn-primary" disabled={draft.trim() === ''}>
          Send
        </button>
      </form>
    </div>
  )
})
