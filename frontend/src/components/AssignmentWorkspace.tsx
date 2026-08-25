import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { Task } from '../types'
import { useSetTaskLinks, useSetTaskNotes } from '../hooks/useTasks'
import { useFormattableEditable, useFormattingContext, type FormatKind } from '../context/FormattingContext'
import { useSyncEditableContent } from '../hooks/useSyncEditableContent'

interface Props {
  task: Task
  onBack: () => void
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

const FORMAT_BUTTONS: Array<{ kind: FormatKind; title: string; glyph: React.ReactNode }> = [
  { kind: 'bold', title: 'Bold (Ctrl/Cmd+B)', glyph: <b>B</b> },
  { kind: 'italic', title: 'Italic (Ctrl/Cmd+I)', glyph: <i>I</i> },
  { kind: 'underline', title: 'Underline (Ctrl/Cmd+U)', glyph: <u>U</u> },
]

const FONT_SIZE_PRESETS_PX = [12, 14, 16, 18, 20, 24, 28, 32, 40]

// Full-page focused writing space for a single assessment - deliberately
// shows nothing else from the main app (no task list, entry form, sidebar,
// or scratchpad), the same way AuthPage replaces TaskListPage wholesale (see
// App.tsx). Mounted/unmounted by TaskListPage, which also owns the
// AnimatePresence + slide transition around it.
export function AssignmentWorkspace({ task, onBack }: Props) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const handle = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(handle)
  }, [])

  const [draft, setDraft] = useState(task.notes ?? '')
  const dirty = useRef(false)
  const setTaskNotes = useSetTaskNotes()
  const setTaskLinks = useSetTaskLinks()

  const onChange = (value: string) => {
    dirty.current = true
    setDraft(value)
  }

  const notesField = useFormattableEditable(onChange)
  useSyncEditableContent(notesField.ref, draft, () => dirty.current)
  // Bold/Italic/Underline buttons below act on whichever editor is
  // currently registered as focused (see FormattingContext) - the same
  // mechanism the sidebar's own B/I/U buttons use for the scratchpad/notes
  // fields, needed here too since this page has no sidebar to borrow them
  // from, and touch devices (iPad) have no Ctrl/Cmd+B-style shortcut.
  const { active: formattingActive, applyFormat } = useFormattingContext()

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
      } else {
        savedRangeRef.current = range.cloneRange()
        setHasSelection(true)
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

  useEffect(() => {
    if (!dirty.current) setDraft(task.notes ?? '')
  }, [task.notes])

  useEffect(() => {
    if (!dirty.current) return
    const handle = setTimeout(() => {
      dirty.current = false
      setTaskNotes.mutate({ id: task.id, notes: draft })
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, 600)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  const remainingMs = task.due_date ? deadlineFor(task.due_date).getTime() - now.getTime() : null

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
          and hard to hit precisely on a touch screen. */}
      <button type="button" className="assignment-workspace-back-zone" title="Back" onClick={onBack}>
        <span className="assignment-workspace-back-icon">←</span>
      </button>

      <div className="assignment-workspace-header">
        <h1 className="assignment-workspace-title">{task.text}</h1>
        {remainingMs !== null ? (
          <p className={remainingMs < 0 ? 'assignment-countdown overdue' : 'assignment-countdown'}>
            {formatRemaining(remainingMs)}
          </p>
        ) : (
          <p className="assignment-countdown no-due-date">No due date set</p>
        )}
      </div>

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

      <div className="assignment-toolbar" data-focus-exempt>
        <div className="assignment-toolbar-group">
          {FORMAT_BUTTONS.map(({ kind, title, glyph }) => (
            <button
              key={kind}
              type="button"
              className={formattingActive ? 'icon-btn btn-primary' : 'icon-btn'}
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
              Font size
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
        onKeyDown={notesField.onKeyDown}
      />
    </motion.div>
  )
}
