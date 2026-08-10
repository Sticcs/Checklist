import { createContext, useCallback, useContext, useRef, useState, type ReactNode, type RefObject } from 'react'
import { toggleMarkdownFormat, type FormatKind } from '../utils/markdownFormat'

interface ActiveEditor {
  ref: RefObject<HTMLTextAreaElement | null>
  setValue: (value: string) => void
}

interface FormattingContextValue {
  active: boolean
  applyFormat: (kind: FormatKind) => void
  registerFocus: (editor: ActiveEditor) => void
  registerBlur: (ref: RefObject<HTMLTextAreaElement | null>) => void
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

  const registerBlur = useCallback((ref: RefObject<HTMLTextAreaElement | null>) => {
    // Only clear if this blur came from whichever editor is still the
    // current one - otherwise a stale blur (e.g. from an editor that lost
    // focus a while ago) could clobber a newer editor's active state.
    if (activeEditorRef.current?.ref === ref) {
      activeEditorRef.current = null
      setActive(false)
    }
  }, [])

  const applyFormat = useCallback((kind: FormatKind) => {
    const editor = activeEditorRef.current
    const el = editor?.ref.current
    if (!editor || !el) return
    const result = toggleMarkdownFormat(el, kind)
    editor.setValue(result.value)
    // The textarea is a controlled component, so writing el.value directly
    // would just get overwritten by the re-render triggered above - restore
    // the selection after that render lands instead of before it.
    requestAnimationFrame(() => {
      el.focus()
      el.setSelectionRange(result.selectionStart, result.selectionEnd)
    })
  }, [])

  return (
    <FormattingContext.Provider value={{ active, applyFormat, registerFocus, registerBlur }}>
      {children}
    </FormattingContext.Provider>
  )
}

export function useFormattingContext() {
  const ctx = useContext(FormattingContext)
  if (!ctx) throw new Error('useFormattingContext must be used within a FormattingProvider')
  return ctx
}

// Spread the returned handlers onto a <textarea>: it registers as the active
// editor on focus, and Ctrl/Cmd+B/I/U format the current selection in place.
export function useFormattableTextarea(setValue: (value: string) => void) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const { registerFocus, registerBlur, applyFormat } = useFormattingContext()

  const onFocus = () => registerFocus({ ref, setValue })
  const onBlur = () => registerBlur(ref)

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!(e.ctrlKey || e.metaKey)) return
    const kind: FormatKind | null =
      e.key.toLowerCase() === 'b' ? 'bold' : e.key.toLowerCase() === 'i' ? 'italic' : e.key.toLowerCase() === 'u' ? 'underline' : null
    if (!kind) return
    e.preventDefault()
    applyFormat(kind)
  }

  return { ref, onFocus, onBlur, onKeyDown }
}
