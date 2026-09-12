import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import type { ListEntry, Task } from '../types'
import { useAddTask, useDeleteTask, useToggleDone } from '../hooks/useTasks'
import {
  useCreateListShareLink,
  useDeleteList,
  useRegenerateListShareLink,
  useRenameList,
  useRevokeListShareLink,
} from '../hooks/useLists'
import { LIST_ITEM_CATEGORY, SHOPPING_CATEGORY } from '../constants'
import { useDraftText } from '../hooks/useDraftText'
import { copyTextToClipboard, formatAsOutline } from '../utils/copyAsText'

interface Props {
  list: ListEntry
  items: Task[]
}

// Unifies the built-in Shopping tab and every user-created ("custom") list
// into one bare check+text+delete panel - same simplicity ShoppingPanel
// always had, now with its own add-item box and a "⋮" menu (rename/delete/
// share) that both kinds share, per the backend's unified `lists` model
// (see backend/app/crud.py's Lists section for why Shopping and custom
// lists can share this one component despite finding their items
// differently under the hood).
export function ListPanel({ list, items }: Props) {
  const toggleDone = useToggleDone()
  const deleteTask = useDeleteTask()
  const addTask = useAddTask()
  const renameList = useRenameList()
  const deleteList = useDeleteList()
  const createShareLink = useCreateListShareLink()
  const regenerateShareLink = useRegenerateListShareLink()
  const revokeShareLink = useRevokeListShareLink()

  // Keyed per-list so a draft in one list's add-item box doesn't bleed into
  // another's, and survives a reload the same way the main quick-add does.
  const [newItemText, setNewItemText] = useDraftText(`list-item:${list.id}`)
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [renameDraft, setRenameDraft] = useState(list.name)
  const [sharePopoverOpen, setSharePopoverOpen] = useState(false)
  const [shareLink, setShareLink] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [menuOpen])

  // Reset any stale draft/link state whenever the active list itself
  // changes (switching tabs reuses this same component instance).
  useEffect(() => {
    setRenaming(false)
    setRenameDraft(list.name)
    setSharePopoverOpen(false)
    setShareLink(null)
  }, [list.id, list.name])

  useEffect(() => {
    if (!sharePopoverOpen) return
    createShareLink.mutate(list.id, { onSuccess: (res) => setShareLink(res.url) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sharePopoverOpen, list.id])

  const submitItem = (e: React.FormEvent) => {
    e.preventDefault()
    const text = newItemText.trim()
    if (!text) return
    setNewItemText('')
    if (list.kind === 'shopping') {
      addTask.mutate({ text, priority: 'Medium', category: SHOPPING_CATEGORY, dueDate: null })
    } else {
      addTask.mutate({ text, priority: 'Medium', category: LIST_ITEM_CATEGORY, dueDate: null, listId: list.id })
    }
  }

  const commitRename = () => {
    const name = renameDraft.trim()
    setRenaming(false)
    if (!name || name === list.name) {
      setRenameDraft(list.name)
      return
    }
    renameList.mutate({ id: list.id, name })
  }

  const handleDelete = () => {
    setMenuOpen(false)
    const confirmed = window.confirm(
      list.kind === 'shopping'
        ? 'Clear every item in Shopping? The tab itself stays.'
        : `Delete "${list.name}"? This removes the list and every item in it.`
    )
    if (!confirmed) return
    deleteList.mutate({ id: list.id, kind: list.kind })
  }

  const copyShareLink = async () => {
    if (!shareLink) return
    try {
      await navigator.clipboard.writeText(shareLink)
      toast('🔗 Link copied')
    } catch {
      toast.error("Couldn't copy - try selecting the link and copying manually")
    }
  }

  const handleCopyAsText = async () => {
    const text = formatAsOutline(
      list.name,
      items.map((i) => i.text)
    )
    const ok = await copyTextToClipboard(text)
    if (ok) toast.success('Copied to clipboard')
    else toast.error('Could not copy to clipboard')
  }

  return (
    <div className="assessments-panel">
      <div className="list-panel-header">
        {renaming ? (
          <input
            className="list-rename-input"
            value={renameDraft}
            autoFocus
            onChange={(e) => setRenameDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') {
                setRenameDraft(list.name)
                setRenaming(false)
              }
            }}
          />
        ) : (
          <p className="assessments-heading list-panel-title">{list.name}</p>
        )}
        <div className="list-menu" ref={menuRef} data-focus-exempt>
          <button
            type="button"
            className="compact-menu-btn"
            aria-expanded={menuOpen}
            title="List options"
            onClick={() => setMenuOpen((open) => !open)}
          >
            ⋮
          </button>
          {menuOpen && (
            <div className="compact-menu-popover" data-focus-exempt>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false)
                  setRenaming(true)
                }}
              >
                ✏️ Rename
              </button>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false)
                  setSharePopoverOpen((open) => !open)
                }}
              >
                🔗 Share
              </button>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false)
                  void handleCopyAsText()
                }}
              >
                📄 Copy as text
              </button>
              <button type="button" onClick={handleDelete}>
                🗑️ {list.kind === 'shopping' ? 'Clear all' : 'Delete'}
              </button>
            </div>
          )}
          {sharePopoverOpen && (
            <div className="assignment-share-popover" data-focus-exempt>
              {shareLink ? (
                <>
                  <div className="assignment-share-link-row">
                    <input readOnly value={shareLink} onFocus={(e) => e.currentTarget.select()} />
                    <button type="button" className="btn-primary" onClick={() => void copyShareLink()}>
                      Copy
                    </button>
                  </div>
                  <div className="assignment-share-link-actions">
                    <button
                      type="button"
                      onClick={() =>
                        regenerateShareLink.mutate(list.id, { onSuccess: (res) => setShareLink(res.url) })
                      }
                    >
                      Regenerate
                    </button>
                    <button
                      type="button"
                      onClick={() => revokeShareLink.mutate(list.id, { onSuccess: () => setShareLink(null) })}
                    >
                      Revoke
                    </button>
                  </div>
                </>
              ) : (
                <button
                  type="button"
                  className="btn-primary"
                  disabled={createShareLink.isPending}
                  onClick={() => createShareLink.mutate(list.id, { onSuccess: (res) => setShareLink(res.url) })}
                >
                  {createShareLink.isPending ? 'Generating…' : 'Generate share link'}
                </button>
              )}
              <p className="status-message">Anyone with this link can view and check items off - no login needed.</p>
            </div>
          )}
        </div>
      </div>

      <form className="assignment-task-add-form" onSubmit={submitItem}>
        <input
          placeholder="Add an item..."
          value={newItemText}
          onChange={(e) => setNewItemText(e.target.value)}
        />
      </form>

      <ul className="shopping-list">
        <AnimatePresence>
          {items.map((item) => (
            <motion.li
              key={item.clientKey ?? item.id}
              layout
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0, overflow: 'hidden' }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className={item.done ? 'shopping-item done' : 'shopping-item'}
            >
              <input
                type="checkbox"
                className="task-done-checkbox"
                checked={item.done}
                title="Mark done"
                onChange={() => toggleDone.mutate({ id: item.id, done: !item.done })}
              />
              <span className={item.done ? 'task-text done' : 'task-text'}>{item.text}</span>
              <button
                type="button"
                className="icon-btn"
                title="Remove from list"
                onClick={() => deleteTask.mutate(item.id)}
              >
                🗑️
              </button>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
      {items.length === 0 && <p className="status-message">No items yet.</p>}
    </div>
  )
}
