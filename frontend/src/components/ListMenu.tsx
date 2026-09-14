import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import type { ListEntry, Task } from '../types'
import {
  useCreateListShareLink,
  useDeleteList,
  useRegenerateListShareLink,
  useRenameList,
  useRevokeListShareLink,
  useSetListSimple,
} from '../hooks/useLists'
import { copyTextToClipboard, formatAsOutline } from '../utils/copyAsText'

interface Props {
  list: ListEntry
  items: Task[]
}

// The list-name/rename-input + "⋮" tricolon menu shared by every list panel
// - originally lived inline in ListPanel.tsx (Shopping's bare UI); extracted
// so the rich, TaskCard-based rendering every other list now gets (see
// TaskListPage's right-panel tabs) can drop in the exact same header/menu
// instead of duplicating its rename/share/copy/delete logic. Shopping is
// the one kind that never shows the rich<->simple toggle - it's always
// simple, not user-convertible (see lists_table's is_simple comment).
export function ListMenu({ list, items }: Props) {
  const renameList = useRenameList()
  const deleteList = useDeleteList()
  const setListSimple = useSetListSimple()
  const createShareLink = useCreateListShareLink()
  const regenerateShareLink = useRegenerateListShareLink()
  const revokeShareLink = useRevokeListShareLink()

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

  // Same idea for the share popover - without this it had no way to close
  // on its own, leaving it stuck open until you dug back into "⋮" and
  // pressed Share again just to toggle it off. menuRef still works here
  // since the share popover renders inside the same .list-menu container.
  useEffect(() => {
    if (!sharePopoverOpen) return
    const handler = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setSharePopoverOpen(false)
    }
    // Registered a tick late (not on this same render's effect pass) -
    // opening this popover happens via the "Share" button inside the
    // tricolon menu, whose onClick also closes that menu in the same
    // click (setMenuOpen(false)). That unmounts the Share button itself
    // mid-click, and the still-bubbling click event then reaches document
    // with a target that's already been removed from menuRef's tree -
    // Node.contains() on a detached node returns false, so an
    // immediately-attached listener would see its own opening click as
    // "outside" and close the popover instantly. Deferring the
    // addEventListener call past the current click (which has already
    // fully finished bubbling by the next tick) avoids catching it at all.
    const id = window.setTimeout(() => document.addEventListener('click', handler), 0)
    return () => {
      window.clearTimeout(id)
      document.removeEventListener('click', handler)
    }
  }, [sharePopoverOpen])

  // Reset any stale draft/link state whenever the active list itself
  // changes (a parent switching tabs can reuse the same component instance
  // for a different list).
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

  const commitRename = () => {
    const name = renameDraft.trim()
    setRenaming(false)
    if (!name || name === list.name) {
      setRenameDraft(list.name)
      return
    }
    renameList.mutate({ id: list.id, name })
  }

  // Shopping and the main list ("List 1") always exist exactly once per
  // account and get silently re-created the moment they're missing (see
  // crud.get_or_create_shopping_list/get_or_create_main_list) - deleting
  // either just clears its items and keeps the row, same backend behavior
  // as clear_all, matching Shopping's own long-standing UI copy.
  const isPermanent = list.kind === 'shopping' || list.kind === 'main'

  const handleDelete = () => {
    setMenuOpen(false)
    const confirmed = window.confirm(
      isPermanent
        ? `Clear every item in "${list.name}"? The tab itself stays.`
        : `Delete "${list.name}"? This removes the list and every item in it - this can't be undone.`
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

  const toggleSimple = () => {
    setMenuOpen(false)
    setListSimple.mutate(
      { id: list.id, isSimple: !list.is_simple },
      {
        onSuccess: (updated) =>
          toast(updated.is_simple ? '📋 Now a simple list' : '✅ Now a rich list'),
      }
    )
  }

  return (
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
            {list.kind !== 'shopping' && (
              <button type="button" onClick={toggleSimple} disabled={setListSimple.isPending}>
                {list.is_simple ? '✅ Make this a rich list' : '📋 Make this a simple list'}
              </button>
            )}
            {list.is_simple && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false)
                  setSharePopoverOpen((open) => !open)
                }}
              >
                🔗 Share
              </button>
            )}
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
              🗑️ {isPermanent ? 'Clear all' : 'Delete'}
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
                    onClick={() => regenerateShareLink.mutate(list.id, { onSuccess: (res) => setShareLink(res.url) })}
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
  )
}
