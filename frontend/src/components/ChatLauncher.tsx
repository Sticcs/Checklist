import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useChatSummary } from '../hooks/useChat'
import { ChatPanel } from './ChatPanel'

interface Props {
  currentUsername?: string
}

// The main screen's equivalent of ChatButton - not scoped to one
// assignment's own workspace, so clicking it first shows a conversation
// list (every assignment you can see, each with its own unread count) via
// useChatSummary; picking one swaps to that assignment's ChatPanel (same
// shared panel ChatButton uses inside the workspace). Structurally the
// same button-ref/panel-ref/click-outside/portal-into-body shape as
// NotificationBell/ChatButton, just with a list screen in front of the panel.
export function ChatLauncher({ currentUsername }: Props) {
  const [open, setOpen] = useState(false)
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const { data, refetch } = useChatSummary()
  const assignments = data?.assignments ?? []
  const totalUnread = assignments.reduce((sum, a) => sum + a.unread_count, 0)
  const selected = assignments.find((a) => a.task_id === selectedTaskId) ?? null

  // The background poll alone (~20s) would otherwise leave a just-created
  // assignment missing from the list for up to that long if you open this
  // right after adding one - refetch on open so the list you're actually
  // looking at is never more than a moment stale.
  useEffect(() => {
    if (open) void refetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (!buttonRef.current?.contains(target) && !panelRef.current?.contains(target)) setOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [open])

  // A selected assignment that's no longer in the list (e.g. its share
  // link was revoked while this was open) shouldn't leave the panel
  // pointing at a conversation that no longer exists - same "don't leave a
  // stale selection around" reasoning used elsewhere in this app. Keyed off
  // the ids actually present (a stable, joined string), not the `data`
  // array itself, which is a fresh reference on every fetch even when its
  // contents haven't meaningfully changed.
  const assignmentIdsKey = assignments.map((a) => a.task_id).join(',')
  useEffect(() => {
    if (selectedTaskId !== null && !assignments.some((a) => a.task_id === selectedTaskId)) {
      setSelectedTaskId(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTaskId, assignmentIdsKey])

  const closeAll = () => {
    setOpen(false)
    setSelectedTaskId(null)
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
        {totalUnread > 0 && <span className="notification-badge">{totalUnread > 9 ? '9+' : totalUnread}</span>}
      </button>

      {open &&
        createPortal(
          selected ? (
            <ChatPanel
              ref={panelRef}
              taskId={selected.task_id}
              currentUsername={currentUsername}
              title={selected.text}
              // Closing one open conversation returns to the list (not a
              // full close) - closeAll is reserved for the list view's own
              // "✕", which is the one that actually leaves the launcher.
              onClose={() => setSelectedTaskId(null)}
            />
          ) : (
            <div ref={panelRef} className="assignment-chat-panel" data-focus-exempt>
              <div className="assignment-chat-panel-header">
                <p className="assessments-heading">💬 Chats</p>
                <button type="button" className="icon-btn" title="Close" onClick={closeAll}>
                  ✕
                </button>
              </div>
              <div className="assignment-chat-conversation-list">
                {assignments.length === 0 && (
                  <p className="status-message">No assignments yet - start one to chat about it.</p>
                )}
                {assignments.map((a) => (
                  <button
                    type="button"
                    key={a.task_id}
                    className="assignment-chat-conversation-row"
                    onClick={(e) => {
                      // stopPropagation matters here, not just handling the
                      // click - selecting a conversation swaps this row's
                      // whole list view out for ChatPanel in the same
                      // render, detaching this button from the DOM before
                      // the still-bubbling click reaches the document-level
                      // outside-click listener above; contains() on a
                      // detached node reads as "outside" and closes the
                      // whole panel instead of switching screens. Same race
                      // as ListMenu/TaskCard's Move-to submenu elsewhere in
                      // this app - stopPropagation is the direct fix.
                      e.stopPropagation()
                      setSelectedTaskId(a.task_id)
                    }}
                  >
                    <span className="assignment-chat-conversation-text">
                      {a.text}
                      {!a.is_owner && <span className="shared-assessment-owner"> (shared with you)</span>}
                    </span>
                    {a.unread_count > 0 && (
                      <span className="notification-badge assignment-chat-conversation-badge">
                        {a.unread_count > 9 ? '9+' : a.unread_count}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ),
          document.body
        )}
    </>
  )
}
