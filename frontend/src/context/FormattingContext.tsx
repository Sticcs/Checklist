import { createContext, useCallback, useContext, useRef, useState, type ReactNode, type RefObject } from 'react'

export type FormatKind = 'bold' | 'italic' | 'underline' | 'insertUnorderedList'

const COMMAND: Record<FormatKind, string> = {
  bold: 'bold',
  italic: 'italic',
  underline: 'underline',
  insertUnorderedList: 'insertUnorderedList',
}

interface ActiveEditor {
  ref: RefObject<HTMLDivElement | null>
}

interface FormattingContextValue {
  active: boolean
  applyFormat: (kind: FormatKind) => void
  applyForeColor: (color: string) => void
  registerFocus: (editor: ActiveEditor) => void
  registerBlur: (ref: RefObject<HTMLDivElement | null>) => void
}

const FormattingContext = createContext<FormattingContextValue | null>(null)

// One shared "which of the scratchpad / a subtask notepad / a task's notes
// is currently focused" tracker, so the Bold/Italic/Underline buttons in the
// sidebar (see Sidebar.tsx) can act on whichever of those the user is
// actually typing into, and light up only while one of them has focus.
export function FormattingProvider({ children }: { children: ReactNode }) {
  const activeEditorRef = useRef<ActiveEditor | null>(null)
  const [active, setActive] = useState(false)

  const registerFocus = useCallback((editor: ActiveEditor) => {
    activeEditorRef.current = editor
    setActive(true)
  }, [])

  const registerBlur = useCallback((ref: RefObject<HTMLDivElement | null>) => {
    // Only clear if this blur came from whichever editor is still the
    // current one - otherwise a stale blur (e.g. from an editor that lost
    // focus a while ago) could clobber a newer editor's active state.
    if (activeEditorRef.current?.ref === ref) {
      activeEditorRef.current = null
      setActive(false)
    }
  }, [])

  const applyFormat = useCallback((kind: FormatKind) => {
    const el = activeEditorRef.current?.ref.current
    if (!el) return
    el.focus()
    // The browser's own selection-aware toggle - genuinely renders bold/
    // italic/underline (unlike the old <textarea>-based version, which could
    // only ever insert literal **markdown** characters around plain text,
    // since a <textarea> has no way to render styled text at all).
    // execCommand is deprecated but has no shipping replacement for this;
    // still universally supported, including inside WebView2/WKWebView.
    document.execCommand(COMMAND[kind])
  }, [])

  // Separate from applyFormat since foreColor takes a value (unlike bold/
  // italic/underline/insertUnorderedList, which are plain toggles) - same
  // "act on whichever editor is currently registered as focused" mechanism
  // otherwise.
  const applyForeColor = useCallback((color: string) => {
    const el = activeEditorRef.current?.ref.current
    if (!el) return
    el.focus()
    document.execCommand('foreColor', false, color)
  }, [])

  return (
    <FormattingContext.Provider value={{ active, applyFormat, applyForeColor, registerFocus, registerBlur }}>
      {children}
    </FormattingContext.Provider>
  )
}

export function useFormattingContext() {
  const ctx = useContext(FormattingContext)
  if (!ctx) throw new Error('useFormattingContext must be used within a FormattingProvider')
  return ctx
}

// Spread the returned handlers onto a contentEditable <div>: it registers as
// the active editor on focus, Ctrl/Cmd+B/I/U format the current selection in
// place, and its HTML content is reported out via onInput. Deliberately
// one-way/uncontrolled - see useSyncEditableContent for the matching "write
// content back in" half, used only for changes that didn't come from this
// element's own typing.
export function useFormattableEditable(onChange: (html: string) => void) {
  const ref = useRef<HTMLDivElement>(null)
  const { registerFocus, registerBlur, applyFormat } = useFormattingContext()

  const onFocus = () => {
    registerFocus({ ref })
    // Makes Enter produce a plain <br> instead of Chrome's default of
    // wrapping each line in its own nested <div> - simpler, more predictable
    // stored HTML for what's meant to be a plain paragraph of notes, not
    // richly structured content.
    document.execCommand('defaultParagraphSeparator', false, 'br')
  }
  const onBlur = () => registerBlur(ref)

  const onInput = (e: React.FormEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    // Backspacing everything can leave a stray <br> or empty nested element
    // behind instead of a truly empty element, which would otherwise defeat
    // the CSS :empty placeholder (see .rich-text-input:empty::before).
    if (el.textContent === '') el.innerHTML = ''
    onChange(el.innerHTML)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!(e.ctrlKey || e.metaKey)) return
    const key = e.key.toLowerCase()
    const kind: FormatKind | null = key === 'b' ? 'bold' : key === 'i' ? 'italic' : key === 'u' ? 'underline' : null
    if (!kind) return
    e.preventDefault()
    applyFormat(kind)
  }

  return { ref, onFocus, onBlur, onInput, onKeyDown }
}
