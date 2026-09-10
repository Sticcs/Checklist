import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import type { Task, TasksResponse, WorkspacePage } from '../types'
import { TASKS_KEY, isOwnedTask, setSharedData, useSetTaskLinks, useSetTaskPages, useToggleDone } from '../hooks/useTasks'
import { useAddSubtask, useDeleteSubtask, useToggleSubtask } from '../hooks/useSubtasks'
import {
  useCollaborators,
  useCreateShareLink,
  useRegenerateShareLink,
  useRemoveCollaborator,
  useRevokeShareLink,
} from '../hooks/useCollaboration'
import { collaborationApi } from '../api/collaboration'
import { ApiError } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useIsDesktopApp } from '../hooks/useIsDesktopApp'
import { useFormattableEditable, useFormattingContext, type FormatKind } from '../context/FormattingContext'
import { useSyncEditableContent } from '../hooks/useSyncEditableContent'

const NEW_DOC_URL = 'https://docs.google.com/document/u/0/create?usp=docs_home&ths=true'

interface Props {
  task: Task
  onBack: () => void
  // Only ever called when task.assigned_task_id is non-null - closes the
  // workspace and highlights/scrolls to that parent task back in the main
  // list (see TaskListPage's highlightParentTask).
  onShowParentTask: (taskId: number) => void
}

// A due date is a plain yyyy-mm-dd (no time of day) - the countdown treats
// the assignment as due at the end of that day (23:59:59 local), matching
// how "due today"/"overdue" are already judged everywhere else in the app
// (see daysUntil in dueDatePresets.ts), rather than inventing a separate,
// stricter midnight-start cutoff just for this timer.
function deadlineFor(dueDate: string): Date {
  return new Date(`${dueDate}T23:59:59`)
}

function formatRemaining(ms: number): string {
  const overdue = ms < 0
  const abs = Math.abs(ms)
  const totalSeconds = Math.floor(abs / 1000)
  const days = Math.floor(totalSeconds / 86_400)
  const hours = Math.floor((totalSeconds % 86_400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const parts: string[] = []
  if (days > 0) parts.push(`${days}d`)
  parts.push(`${hours}h`, `${minutes}m`, `${seconds}s`)
  return overdue ? `Overdue by ${parts.join(' ')}` : `${parts.join(' ')} remaining`
}

function normalizeUrl(raw: string): string {
  const trimmed = raw.trim()
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
}

// The very first page, synthesized from the legacy single `notes` field for
// any assignment that predates the pages feature - a stable id (not random)
// so re-deriving this fallback on every render/prop update doesn't churn
// activePageId. Once the user edits or adds a page, the real `pages` array
// gets saved for good (see the pages-sync effect below) and this fallback
// stops being hit.
function defaultFirstPage(notes: string | null): WorkspacePage {
  return { id: 'page-1', title: 'Page 1', content: notes ?? '' }
}

function makePage(title: string): WorkspacePage {
  return { id: `page-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, title, content: '' }
}

const FORMAT_BUTTONS: Array<{ kind: FormatKind; title: string; glyph: React.ReactNode }> = [
  { kind: 'bold', title: 'Bold (Ctrl/Cmd+B)', glyph: <b>B</b> },
  { kind: 'italic', title: 'Italic (Ctrl/Cmd+I)', glyph: <i>I</i> },
  { kind: 'underline', title: 'Underline (Ctrl/Cmd+U)', glyph: <u>U</u> },
]

const FONT_SIZE_PRESETS_PX = [12, 14, 16, 18, 20, 24, 28, 32, 40]
const FONT_SIZE_STEP_PX = 2
const MIN_FONT_SIZE_PX = 8
const MAX_FONT_SIZE_PX = 120

const FONT_COLOR_PRESETS = [
  { label: 'Red', value: '#e74c3c' },
  { label: 'Orange', value: '#e67e22' },
  { label: 'Yellow', value: '#f1c40f' },
  { label: 'Green', value: '#2ecc71' },
  { label: 'Blue', value: '#3498db' },
  { label: 'Purple', value: '#9b59b6' },
  { label: 'Gray', value: '#7f8c8d' },
]

// Semi-transparent (not solid) so whatever's underneath - the card
// background, and critically the text itself - still shows through. A fully
// opaque highlight behind dark mode's near-white default text color made
// the text unreadable; blending with the existing background instead of
// replacing it keeps the page's own contrast mostly intact.
const HIGHLIGHT_COLOR_PRESETS = [
  { label: 'Yellow', value: 'rgba(255, 235, 59, 0.45)' },
  { label: 'Green', value: 'rgba(105, 240, 174, 0.45)' },
  { label: 'Blue', value: 'rgba(100, 181, 246, 0.4)' },
  { label: 'Pink', value: 'rgba(244, 143, 177, 0.4)' },
  { label: 'Orange', value: 'rgba(255, 183, 77, 0.4)' },
]

// Any inline style/attribute that could hardcode a color the current theme
// can't override - pasted content (e.g. from Word or a webpage) routinely
// carries an explicit black (or otherwise theme-clashing) text color, which
// then renders unreadable against a dark background since an inline style
// always wins over this page's own `color: var(--text-primary)`. Stripped
// on every paste (not just Ctrl+Shift+V's plain-text paste) so this can't
// recur; structural formatting (bold/italic/lists/font-size) is left alone.
function stripForcedColors(html: string): string {
  const container = document.createElement('div')
  container.innerHTML = html
  const strip = (el: Element) => {
    if (el instanceof HTMLElement) {
      el.style.removeProperty('color')
      el.style.removeProperty('background')
      el.style.removeProperty('background-color')
      el.style.removeProperty('font-family')
      if (el.getAttribute('style') === '') el.removeAttribute('style')
      if (el.tagName === 'FONT') el.removeAttribute('color')
    }
    for (const child of Array.from(el.children)) strip(child)
  }
  strip(container)
  return container.innerHTML
}

// Full-page focused writing space for a single assessment - deliberately
// shows nothing else from the main app (no task list, entry form, sidebar,
// or scratchpad), the same way AuthPage replaces TaskListPage wholesale (see
// App.tsx). Mounted/unmounted by TaskListPage, which also owns the
// AnimatePresence + slide transition around it.
export function AssignmentWorkspace({ task, onBack, onShowParentTask }: Props) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const handle = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(handle)
  }, [])

  const setTaskLinks = useSetTaskLinks()
  const setTaskPages = useSetTaskPages()
  const toggleDone = useToggleDone()
  const addSubtask = useAddSubtask()
  const toggleSubtask = useToggleSubtask()
  const deleteSubtask = useDeleteSubtask()

  const queryClient = useQueryClient()
  const { user } = useAuth()
  const isDesktopApp = useIsDesktopApp()
  const isOwner = task.username === user?.username

  // Refreshes this one assignment every 20s while the workspace stays open -
  // the app's whole collaboration model is "refresh to see" (no websockets/
  // SSE), so this is the entire mechanism by which a collaborator's edits
  // eventually show up for the owner (and vice versa) without a manual
  // reload. The pages-sync effect below already guards against a poll
  // clobbering in-progress local typing (it only re-syncs from a changed
  // task.pages prop when !dirty.current), so no extra guard is needed here.
  const pollQuery = useQuery({
    queryKey: ['assignment-poll', task.id],
    queryFn: () => collaborationApi.getTask(task.id),
    refetchInterval: 20_000,
    refetchIntervalInBackground: false,
  })

  useEffect(() => {
    const fresh = pollQuery.data
    if (!fresh) return
    if (isOwnedTask(queryClient, fresh.id)) {
      queryClient.setQueryData<TasksResponse>(TASKS_KEY, (old) =>
        old ? { ...old, tasks: old.tasks.map((t) => (t.id === fresh.id ? fresh : t)) } : old
      )
    } else {
      setSharedData(queryClient, (old) => old.map((t) => (t.id === fresh.id ? fresh : t)))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollQuery.data])

  useEffect(() => {
    // 404 means the assignment was deleted, or (for a collaborator) access
    // was revoked - either way there's nothing left to show here.
    if (pollQuery.error instanceof ApiError && pollQuery.error.status === 404) {
      toast.error('This assignment is no longer available')
      onBack()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollQuery.error])

  const [sharePopoverOpen, setSharePopoverOpen] = useState(false)
  const [shareLink, setShareLink] = useState<string | null>(null)
  const createShareLink = useCreateShareLink()
  const regenerateShareLink = useRegenerateShareLink()
  const revokeShareLink = useRevokeShareLink()
  const collaboratorsQuery = useCollaborators(task.id, sharePopoverOpen && isOwner)
  const removeCollaborator = useRemoveCollaborator()

  // Get-or-create is idempotent server-side, so re-fetching every time the
  // popover opens is harmless - it just returns the existing link if one's
  // already active, giving an instant "here's your link" instead of an
  // extra click to generate one.
  useEffect(() => {
    if (!sharePopoverOpen || !isOwner) return
    createShareLink.mutate(task.id, { onSuccess: (res) => setShareLink(res.url) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sharePopoverOpen, isOwner, task.id])

  useEffect(() => {
    if (!sharePopoverOpen) return
    const handler = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('.assignment-share')) setSharePopoverOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [sharePopoverOpen])

  const copyShareLink = async () => {
    if (!shareLink) return
    try {
      await navigator.clipboard.writeText(shareLink)
      toast('🔗 Link copied')
    } catch {
      toast.error("Couldn't copy - try selecting the link and copying manually")
    }
  }

  const handleGenerateLink = () => {
    createShareLink.mutate(task.id, { onSuccess: (res) => setShareLink(res.url) })
  }

  const handleRegenerateLink = () => {
    regenerateShareLink.mutate(task.id, { onSuccess: (res) => setShareLink(res.url) })
  }

  const handleRevokeLink = () => {
    revokeShareLink.mutate(task.id, { onSuccess: () => setShareLink(null) })
  }

  // Multiple pages (Word/Docs-style tabs) per assignment - each its own
  // rich-text doc. `pages` is the working copy (kept in sync with
  // task.pages below, same "only sync while not mid-edit" pattern the old
  // single-notes-field version used); `draft` mirrors just the *active*
  // page's content, since that's the one piece bound to the contentEditable
  // box via useSyncEditableContent.
  const [pages, setPages] = useState<WorkspacePage[]>(() =>
    task.pages.length > 0 ? task.pages : [defaultFirstPage(task.notes)]
  )
  const [activePageId, setActivePageId] = useState(() => pages[0].id)
  const [draft, setDraft] = useState(() => pages[0].content)
  const dirty = useRef(false)

  useEffect(() => {
    if (dirty.current) return
    const serverPages = task.pages.length > 0 ? task.pages : [defaultFirstPage(task.notes)]
    setPages(serverPages)
    const nextId = serverPages.some((p) => p.id === activePageId) ? activePageId : serverPages[0].id
    setActivePageId(nextId)
    setDraft(serverPages.find((p) => p.id === nextId)?.content ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.pages, task.notes])

  useEffect(() => {
    if (!dirty.current) return
    const handle = setTimeout(() => {
      dirty.current = false
      setTaskPages.mutate({ id: task.id, pages })
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, 600)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pages])

  const onChange = (value: string) => {
    dirty.current = true
    setDraft(value)
    setPages((prev) => prev.map((p) => (p.id === activePageId ? { ...p, content: value } : p)))
  }

  const switchPage = (id: string) => {
    if (id === activePageId) return
    setActivePageId(id)
    setDraft(pages.find((p) => p.id === id)?.content ?? '')
  }

  const addPage = () => {
    const page = makePage(`Page ${pages.length + 1}`)
    const next = [...pages, page]
    setPages(next)
    setActivePageId(page.id)
    setDraft('')
    setTaskPages.mutate({ id: task.id, pages: next })
  }

  const deletePage = (id: string) => {
    if (pages.length <= 1) return
    const next = pages.filter((p) => p.id !== id)
    setPages(next)
    if (activePageId === id) {
      setActivePageId(next[0].id)
      setDraft(next[0].content)
    }
    setTaskPages.mutate({ id: task.id, pages: next })
  }

  const notesField = useFormattableEditable(onChange)
  useSyncEditableContent(notesField.ref, draft, () => dirty.current)
  // Bold/Italic/Underline buttons below act on whichever editor is
  // currently registered as focused (see FormattingContext) - the same
  // mechanism the sidebar's own B/I/U buttons use for the scratchpad/notes
  // fields, needed here too since this page has no sidebar to borrow them
  // from, and touch devices (iPad) have no Ctrl/Cmd+B-style shortcut.
  const { active: formattingActive, applyFormat, applyForeColor } = useFormattingContext()

  // Font size only ever applies to highlighted text (like a word processor's
  // size dropdown), never the whole box - so unlike bold/italic/underline
  // (which act on "whichever editor is focused"), this needs its own record
  // of the last real *selection* made inside the textbox specifically, kept
  // alive even after focus moves to the dropdown/custom-size input (both of
  // which must steal focus to be usable/accessible at all, unlike the
  // mousedown-preventDefault trick the format buttons use).
  const [hasSelection, setHasSelection] = useState(false)
  const savedRangeRef = useRef<Range | null>(null)
  const [customSizeOpen, setCustomSizeOpen] = useState(false)
  const [customSizeValue, setCustomSizeValue] = useState('')
  // A live readout of the highlighted text's own font size - null when
  // nothing's selected, so the toolbar can show "16px" etc instead of a
  // static "Font size" placeholder.
  const [currentFontSizePx, setCurrentFontSizePx] = useState<number | null>(null)

  useEffect(() => {
    const handler = () => {
      const el = notesField.ref.current
      const sel = window.getSelection()
      if (!el || !sel || sel.rangeCount === 0) return
      const range = sel.getRangeAt(0)
      // A selection change caused by focusing the size dropdown/input isn't
      // inside the textbox at all - ignore it and keep whatever was last
      // highlighted there, rather than treating it as "selection cleared".
      if (!el.contains(range.commonAncestorContainer)) return
      if (sel.isCollapsed) {
        setHasSelection(false)
        savedRangeRef.current = null
        setCurrentFontSizePx(null)
      } else {
        savedRangeRef.current = range.cloneRange()
        setHasSelection(true)
        const startNode = range.startContainer
        const startEl = startNode.nodeType === Node.ELEMENT_NODE ? (startNode as Element) : startNode.parentElement
        setCurrentFontSizePx(startEl ? Math.round(Number.parseFloat(getComputedStyle(startEl).fontSize)) || null : null)
      }
    }
    document.addEventListener('selectionchange', handler)
    return () => document.removeEventListener('selectionchange', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const applyFontSizeToSelection = (px: number) => {
    const el = notesField.ref.current
    const range = savedRangeRef.current
    const sel = window.getSelection()
    if (!el || !range || !sel || !Number.isFinite(px) || px <= 0) return
    el.focus()
    sel.removeAllRanges()
    sel.addRange(range)
    // execCommand('fontSize') only accepts the legacy 1-7 scale, so 7 (the
    // largest) is used purely as a unique marker to find the element(s) it
    // just wrapped the selection in, which are then restyled with the exact
    // px value requested instead of whatever "7" would otherwise mean.
    document.execCommand('fontSize', false, '7')
    el.querySelectorAll('font[size="7"]').forEach((node) => {
      const f = node as HTMLElement
      f.removeAttribute('size')
      f.style.fontSize = `${px}px`
    })
    // execCommand mutates the DOM directly - it fires the 'input' event that
    // onInput normally relies on, but the *subsequent* manual restyling above
    // does not, so the draft state needs an explicit refresh to pick up the
    // corrected markup (otherwise the debounced autosave would persist the
    // pre-restyle <font size="7"> instead of the actual chosen size).
    onChange(el.innerHTML)
    setCurrentFontSizePx(px)
  }

  // Ctrl/Cmd+Shift+. / Ctrl/Cmd+Shift+, - reads the size off the selection's
  // own start element (not a fixed default) so repeated presses actually
  // step up/down from wherever that text already is, matching how a word
  // processor's own size-step shortcuts behave.
  const stepFontSize = (direction: 1 | -1) => {
    const range = savedRangeRef.current
    if (!range) return
    const startNode = range.startContainer
    const el = startNode.nodeType === Node.ELEMENT_NODE ? (startNode as Element) : startNode.parentElement
    const current = el ? Number.parseFloat(getComputedStyle(el).fontSize) || 16 : 16
    const next = Math.min(MAX_FONT_SIZE_PX, Math.max(MIN_FONT_SIZE_PX, current + direction * FONT_SIZE_STEP_PX))
    applyFontSizeToSelection(next)
  }

  const [colorPickerOpen, setColorPickerOpen] = useState(false)

  useEffect(() => {
    if (!colorPickerOpen) return
    const handler = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('.assignment-toolbar-color')) setColorPickerOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [colorPickerOpen])

  const applyForeColorToSelection = (color: string) => {
    const el = notesField.ref.current
    const range = savedRangeRef.current
    const sel = window.getSelection()
    if (!el || !range || !sel) return
    el.focus()
    sel.removeAllRanges()
    sel.addRange(range)
    applyForeColor(color)
    setColorPickerOpen(false)
  }

  const [highlightPickerOpen, setHighlightPickerOpen] = useState(false)
  // The main 🖍️ button applies this directly (no picker needed) - clicking
  // a swatch in the dropdown both applies it and remembers it as the new
  // one-click default, the same "highlighter" behavior Docs/Word use.
  const [lastHighlightColor, setLastHighlightColor] = useState(HIGHLIGHT_COLOR_PRESETS[0].value)

  useEffect(() => {
    if (!highlightPickerOpen) return
    const handler = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('.assignment-toolbar-highlight')) setHighlightPickerOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [highlightPickerOpen])

  // backColor (not the Firefox-only hiliteColor) - same execCommand family
  // as fontSize/foreColor above, universally supported here too.
  const applyHighlightToSelection = (color: string) => {
    const el = notesField.ref.current
    const range = savedRangeRef.current
    const sel = window.getSelection()
    if (!el || !range || !sel) return
    el.focus()
    sel.removeAllRanges()
    sel.addRange(range)
    document.execCommand('backColor', false, color)
    setLastHighlightColor(color)
    setHighlightPickerOpen(false)
  }

  // The browser's own contentEditable undo/redo history - already tracks
  // every typed keystroke and execCommand-driven change (bold, font size,
  // color, paste...) with no extra bookkeeping needed here.
  const undoEdit = () => {
    notesField.ref.current?.focus()
    document.execCommand('undo')
  }
  const redoEdit = () => {
    notesField.ref.current?.focus()
    document.execCommand('redo')
  }

  // Ctrl/Cmd+Shift+V: reads the clipboard directly (a custom shortcut like
  // this never fires a native 'paste' event the way Ctrl/Cmd+V does) and
  // inserts it via insertText, which - unlike insertHTML - can't carry any
  // formatting/color along even if the source had some.
  const pasteAsPlainText = async () => {
    try {
      const text = await navigator.clipboard.readText()
      notesField.ref.current?.focus()
      document.execCommand('insertText', false, text)
    } catch {
      toast.error("Couldn't read the clipboard - your browser may need permission")
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const withMod = e.ctrlKey || e.metaKey
    if (withMod && e.shiftKey && (e.code === 'Period' || e.code === 'Comma')) {
      e.preventDefault()
      stepFontSize(e.code === 'Period' ? 1 : -1)
      return
    }
    if (withMod && e.shiftKey && e.key.toLowerCase() === 'v') {
      e.preventDefault()
      void pasteAsPlainText()
      return
    }
    notesField.onKeyDown(e)
  }

  // The default (Ctrl/Cmd+V) paste path - unlike Ctrl+Shift+V, this keeps
  // structural formatting (bold/italic/lists/font-size) from the source,
  // but strips any hardcoded color so pasted text can't silently render
  // unreadable against the current theme (see stripForcedColors).
  const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    e.preventDefault()
    const html = e.clipboardData.getData('text/html')
    if (html) {
      document.execCommand('insertHTML', false, stripForcedColors(html))
    } else {
      document.execCommand('insertText', false, e.clipboardData.getData('text/plain'))
    }
  }

  const [linksOpen, setLinksOpen] = useState(false)
  const [linkName, setLinkName] = useState('')
  const [linkUrl, setLinkUrl] = useState('')

  const submitLink = (e: React.FormEvent) => {
    e.preventDefault()
    const name = linkName.trim()
    const url = linkUrl.trim()
    if (!name || !url) return
    setTaskLinks.mutate({ id: task.id, links: [...task.links, { name, url: normalizeUrl(url) }] })
    setLinkName('')
    setLinkUrl('')
    setLinksOpen(false)
  }

  const removeLink = (index: number) => {
    setTaskLinks.mutate({ id: task.id, links: task.links.filter((_, i) => i !== index) })
  }

  // innerText (not innerHTML/textContent) so the copied text keeps its line
  // breaks matching what's actually visible in the box - textContent would
  // flatten every <div>/<br> the rich-text editing produces onto one line.
  const copyAsText = async () => {
    const text = notesField.ref.current?.innerText ?? ''
    try {
      await navigator.clipboard.writeText(text)
      toast('📋 Copied as plain text')
    } catch {
      toast.error("Couldn't copy - try selecting the text and copying manually")
    }
  }

  // A separate, deliberately bare-bones task list scoped to this one
  // assignment - reuses the exact same subtask entity/mutations as a normal
  // task's subtask panel (TaskCard), just with a much smaller UI: no due
  // dates, priority, or notes, only text + done. Typing in the box above
  // and pressing Enter is the entire add flow, no multi-step wizard.
  const [newTaskText, setNewTaskText] = useState('')
  const submitTask = (e: React.FormEvent) => {
    e.preventDefault()
    const text = newTaskText.trim()
    if (!text) return
    setNewTaskText('')
    addSubtask.mutate({ taskId: task.id, text })
  }

  const remainingMs = task.due_date ? deadlineFor(task.due_date).getTime() - now.getTime() : null
  // dirty is a plain ref (not state) since the debounce logic above already
  // needs it to read as current-not-stale inside effects/timeouts - reading
  // it here during render is safe because every actual transition (typing,
  // the debounce firing into setTaskPages.mutate) already triggers a
  // re-render of its own (setDraft, or react-query's isPending flipping),
  // so this never needs its own state to stay in sync.
  const isSaving = dirty.current || setTaskPages.isPending

  const toggleFinished = () => {
    const next = !task.done
    toggleDone.mutate({ id: task.id, done: next })
    toast(next ? '✅ Marked as finished' : '↩️ Marked as not finished')
  }

  return (
    <motion.div
      className="assignment-workspace"
      // The task-list page's document-level click handler (see
      // TaskListPage) treats any click outside a task card as "clear
      // focus" - without this, clicking anywhere in here (the textbox, the
      // toolbar, the back zone) would clear the assessment's focused/
      // selected state in the background, so it'd no longer show as
      // selected (and its Start button/badges would vanish) the moment you
      // go back.
      data-focus-exempt
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 40 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
    >
      {/* A large tap/click zone (not just the small arrow glyph) running the
          full height of the left edge - the glyph alone was easy to miss
          and hard to hit precisely on a touch screen. Positioned relative to
          .assignment-workspace, which no longer scrolls itself (only the
          textbox does - see .assignment-workspace-textbox), so this stays
          on screen the same way the rest of the chrome does, with no extra
          "stickiness" of its own needed. */}
      <button type="button" className="assignment-workspace-back-zone" title="Back" onClick={onBack}>
        <span className="assignment-workspace-back-icon">←</span>
      </button>

      <div className="assignment-workspace-main">
        <div className="assignment-top-actions">
          <div className="assignment-top-actions-left">
            {task.assigned_task_id !== null && (
              <button
                type="button"
                className="assignment-add-link-btn"
                title="Show the task this is assigned under"
                onClick={() => onShowParentTask(task.assigned_task_id!)}
              >
                🔗 Assigned under a task
              </button>
            )}

            {isOwner ? (
              isDesktopApp ? (
                <p className="status-message assignment-share-desktop-note">
                  Sharing isn't available in the desktop app - it uses its own offline database, separate
                  from the website's.
                </p>
              ) : (
                <div className="assignment-share" data-focus-exempt>
                  <button
                    type="button"
                    className="assignment-add-link-btn"
                    onClick={() => setSharePopoverOpen((open) => !open)}
                  >
                    🔗 Share
                  </button>
                  {sharePopoverOpen && (
                    <div className="assignment-share-popover" data-focus-exempt>
                      {shareLink ? (
                        <>
                          <div className="assignment-share-link-row">
                            <input
                              readOnly
                              value={shareLink}
                              onFocus={(e) => e.currentTarget.select()}
                            />
                            <button type="button" className="btn-primary" onClick={() => void copyShareLink()}>
                              Copy
                            </button>
                          </div>
                          <div className="assignment-share-link-actions">
                            <button type="button" onClick={handleRegenerateLink}>
                              Regenerate
                            </button>
                            <button type="button" onClick={handleRevokeLink}>
                              Revoke
                            </button>
                          </div>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="btn-primary"
                          disabled={createShareLink.isPending}
                          onClick={handleGenerateLink}
                        >
                          {createShareLink.isPending ? 'Generating…' : 'Generate share link'}
                        </button>
                      )}
                      <p className="assessments-heading assignment-share-collaborators-heading">Collaborators</p>
                      {(collaboratorsQuery.data?.collaborators.length ?? 0) === 0 ? (
                        <p className="status-message">No collaborators yet.</p>
                      ) : (
                        <ul className="assignment-collaborators-list">
                          {collaboratorsQuery.data!.collaborators.map((c) => (
                            <li key={c.username}>
                              <span>{c.username}</span>
                              <button
                                type="button"
                                className="icon-btn"
                                title="Remove collaborator"
                                onClick={() => removeCollaborator.mutate({ taskId: task.id, username: c.username })}
                              >
                                ✕
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              )
            ) : (
              <p className="status-message assignment-shared-by">🤝 Shared by {task.username}</p>
            )}
          </div>
          <button
            type="button"
            className={task.done ? 'assignment-finish-btn done' : 'assignment-finish-btn'}
            onClick={toggleFinished}
          >
            {task.done ? '✅ Finished' : '✅ Mark as Finished'}
          </button>
        </div>

        <div className="assignment-workspace-header-row">
          <div className="assignment-workspace-header">
            <h1 className="assignment-workspace-title">{task.text}</h1>
            {remainingMs !== null ? (
              <p className={remainingMs < 0 ? 'assignment-countdown overdue' : 'assignment-countdown'}>
                {formatRemaining(remainingMs)}
              </p>
            ) : (
              <p className="assignment-countdown no-due-date">No due date set</p>
            )}
            <p className={isSaving ? 'assignment-save-status saving' : 'assignment-save-status'}>
              {isSaving ? '💾 Saving…' : '✅ Saved'}
            </p>
          </div>
        </div>

        {/* One continuous bar (Google Docs/Word style) - every control is a
            flush toolbar-btn with no individual pill border, separated into
            logical groups by a thin divider rather than by visible gaps
            between separately-styled buttons. */}
        <div className="assignment-toolbar" data-focus-exempt>
          <div className="assignment-toolbar-group">
            <button
              type="button"
              className="toolbar-btn"
              title="Undo (Ctrl/Cmd+Z)"
              onMouseDown={(e) => e.preventDefault()}
              onClick={undoEdit}
            >
              ↩️
            </button>
            <button
              type="button"
              className="toolbar-btn"
              title="Redo (Ctrl/Cmd+Shift+Z)"
              onMouseDown={(e) => e.preventDefault()}
              onClick={redoEdit}
            >
              ↪️
            </button>
          </div>

          <span className="assignment-toolbar-divider" />

          <div className="assignment-toolbar-group">
            {FORMAT_BUTTONS.map(({ kind, title, glyph }) => (
              <button
                key={kind}
                type="button"
                className={formattingActive ? 'toolbar-btn active' : 'toolbar-btn'}
                disabled={!formattingActive}
                title={title}
                // Keeps focus (and the selection) inside the textbox instead
                // of moving it to this button, which is what a plain click
                // would do - applyFormat needs that selection intact.
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => applyFormat(kind)}
              >
                {glyph}
              </button>
            ))}
          </div>

          <span className="assignment-toolbar-divider" />

          <div className="assignment-toolbar-group">
            <button
              type="button"
              className={formattingActive ? 'toolbar-btn active' : 'toolbar-btn'}
              disabled={!formattingActive}
              title="Bullet list"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => applyFormat('insertUnorderedList')}
            >
              ☰•
            </button>
            <div className="assignment-toolbar-highlight">
              <button
                type="button"
                className="toolbar-btn"
                disabled={!hasSelection}
                title={hasSelection ? 'Highlight (last used color)' : 'Highlight text to use this'}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => applyHighlightToSelection(lastHighlightColor)}
              >
                🖍️
              </button>
              <button
                type="button"
                className="toolbar-btn toolbar-caret-btn"
                disabled={!hasSelection}
                title="Choose highlight color"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setHighlightPickerOpen((open) => !open)}
              >
                ▾
              </button>
              {highlightPickerOpen && (
                <div className="assignment-color-popover" data-focus-exempt>
                  <button
                    type="button"
                    className="assignment-color-swatch default"
                    title="No highlight"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => applyHighlightToSelection('transparent')}
                  >
                    ✕
                  </button>
                  {HIGHLIGHT_COLOR_PRESETS.map(({ label, value }) => (
                    <button
                      key={value}
                      type="button"
                      className="assignment-color-swatch"
                      style={{ background: value }}
                      title={label}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => applyHighlightToSelection(value)}
                    />
                  ))}
                </div>
              )}
            </div>
            <div className="assignment-toolbar-color">
              <button
                type="button"
                className="toolbar-btn"
                disabled={!hasSelection}
                title={hasSelection ? 'Text color (applies to the highlighted text)' : 'Highlight text to change its color'}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setColorPickerOpen((open) => !open)}
              >
                🎨
              </button>
              {colorPickerOpen && (
                <div className="assignment-color-popover" data-focus-exempt>
                  <button
                    type="button"
                    className="assignment-color-swatch default"
                    title="Default (current theme color)"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() =>
                      applyForeColorToSelection(getComputedStyle(document.body).getPropertyValue('--text-primary').trim())
                    }
                  >
                    A
                  </button>
                  {FONT_COLOR_PRESETS.map(({ label, value }) => (
                    <button
                      key={value}
                      type="button"
                      className="assignment-color-swatch"
                      style={{ background: value }}
                      title={label}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => applyForeColorToSelection(value)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          <span className="assignment-toolbar-divider" />

          <div className="assignment-toolbar-group">
            <select
              className="assignment-fontsize-select"
              disabled={!hasSelection}
              title={hasSelection ? 'Font size (applies to the highlighted text)' : 'Highlight text to change its size'}
              value=""
              onChange={(e) => {
                const val = e.target.value
                if (val === 'custom') setCustomSizeOpen(true)
                else if (val) applyFontSizeToSelection(Number(val))
              }}
            >
              <option value="" disabled>
                {hasSelection && currentFontSizePx !== null ? `${currentFontSizePx}px` : 'Font size'}
              </option>
              {FONT_SIZE_PRESETS_PX.map((px) => (
                <option key={px} value={px}>
                  {px}px
                </option>
              ))}
              <option value="custom">Custom…</option>
            </select>
            {customSizeOpen && (
              <form
                className="assignment-fontsize-custom-form"
                onSubmit={(e) => {
                  e.preventDefault()
                  applyFontSizeToSelection(Number(customSizeValue))
                  setCustomSizeOpen(false)
                  setCustomSizeValue('')
                }}
              >
                <input
                  type="number"
                  min={1}
                  max={300}
                  placeholder="px"
                  autoFocus
                  value={customSizeValue}
                  onChange={(e) => setCustomSizeValue(e.target.value)}
                  onBlur={() => {
                    if (!customSizeValue) setCustomSizeOpen(false)
                  }}
                />
                <button type="submit" className="btn-primary">
                  Apply
                </button>
              </form>
            )}
          </div>

          <span className="assignment-toolbar-divider" />

          <div className="assignment-toolbar-group">
            <button
              type="button"
              className="toolbar-btn"
              title="Copy the write-up as plain text - to paste it in wherever it actually needs to be submitted"
              onClick={() => void copyAsText()}
            >
              📋
            </button>
            <a
              href={NEW_DOC_URL}
              target="_blank"
              rel="noreferrer"
              className="assignment-add-link-btn"
              title="Open a blank Google Doc in a new tab"
            >
              📄 Create new doc
            </a>
          </div>
        </div>

        <div className="assignment-body-row">
          {/* Links (moved up here, above the task panel, so both live in one
              shared left column instead of links sitting up in the header)
              and the bare-bones per-assignment task list - both fixed/
              anchored the same way the rest of the chrome is, only the
              textbox itself scrolls (see .assignment-workspace-textbox). */}
          <div className="assignment-left-column">
            <div className="assignment-links-panel" data-focus-exempt>
              <button
                type="button"
                className="assignment-add-link-btn"
                onClick={() => setLinksOpen((open) => !open)}
              >
                🔗 Add link
              </button>
              <AnimatePresence>
                {linksOpen && (
                  <motion.form
                    className="assignment-add-link-form"
                    onSubmit={submitLink}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <input
                      placeholder="Website name"
                      value={linkName}
                      onChange={(e) => setLinkName(e.target.value)}
                      autoFocus
                    />
                    <input
                      placeholder="https://..."
                      value={linkUrl}
                      onChange={(e) => setLinkUrl(e.target.value)}
                    />
                    <button type="submit" className="btn-primary">
                      Add
                    </button>
                  </motion.form>
                )}
              </AnimatePresence>
              {task.links.length > 0 && (
                <ul className="assignment-links-list">
                  {task.links.map((link, i) => (
                    <li key={`${link.url}-${i}`}>
                      <a href={link.url} target="_blank" rel="noreferrer">
                        {link.name}
                      </a>
                      <button type="button" className="icon-btn" title="Remove link" onClick={() => removeLink(i)}>
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* A deliberately minimal task list scoped to this one assignment
                (see the state/handler above) - typing in the box and pressing
                Enter is the whole add flow, and each row is just a checkbox
                and its text, nothing else. */}
            <div className="assignment-tasks-column" data-focus-exempt>
              <form className="assignment-task-add-form" onSubmit={submitTask}>
                <input
                  placeholder="Add a task..."
                  value={newTaskText}
                  onChange={(e) => setNewTaskText(e.target.value)}
                />
              </form>
              <ul className="assignment-tasks-list">
                <AnimatePresence>
                  {task.subtasks.map((s) => (
                    <motion.li
                      key={s.clientKey ?? s.id}
                      layout
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.18, ease: 'easeOut' }}
                      className={s.done ? 'assignment-task-row done' : 'assignment-task-row'}
                    >
                      <input
                        type="checkbox"
                        className="task-done-checkbox small"
                        checked={s.done}
                        title="Mark complete"
                        onChange={() => toggleSubtask.mutate({ subtaskId: s.id, done: !s.done })}
                      />
                      <span className="assignment-task-text">{s.text}</span>
                      <button
                        type="button"
                        className="assignment-task-delete-btn"
                        title="Delete"
                        onClick={() => deleteSubtask.mutate(s.id)}
                      >
                        ✕
                      </button>
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ul>
              {task.subtasks.length === 0 && <p className="status-message">No tasks yet.</p>}
            </div>
          </div>

          <div className="assignment-textbox-column">
            <div className="assignment-page-tabs" data-focus-exempt>
              {pages.map((page) => (
                <div
                  key={page.id}
                  className={page.id === activePageId ? 'assignment-page-tab active' : 'assignment-page-tab'}
                >
                  <button type="button" onClick={() => switchPage(page.id)}>
                    {page.title}
                  </button>
                  {pages.length > 1 && (
                    <button
                      type="button"
                      className="assignment-page-tab-close"
                      title="Delete this page"
                      onClick={() => deletePage(page.id)}
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
              <button type="button" className="assignment-page-tab-add" title="Add a page" onClick={addPage}>
                + Page
              </button>
            </div>

            <div
              ref={notesField.ref}
              className="assignment-workspace-textbox rich-text-input"
              contentEditable
              suppressContentEditableWarning
              data-placeholder="Start writing..."
              onInput={notesField.onInput}
              onFocus={notesField.onFocus}
              onBlur={notesField.onBlur}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
            />
          </div>
        </div>
      </div>
    </motion.div>
  )
}
