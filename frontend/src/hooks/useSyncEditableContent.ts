import { useEffect, type RefObject } from 'react'

// Imperatively writes `html` into a contentEditable element - but only when
// `isDirty()` returns false (evaluated at effect-run time, so it can check
// e.g. document.activeElement freshly) and the DOM doesn't already match.
// Never while the user is actively typing into it: reflecting a
// contentEditable's content back in as a React-controlled value (the way a
// <textarea>'s value prop works) resets the caret to the start on every
// keystroke, since React can't diff into an "opaque" contentEditable subtree
// the way it does normal children.
export function useSyncEditableContent(ref: RefObject<HTMLDivElement | null>, html: string, isDirty: () => boolean) {
  useEffect(() => {
    if (isDirty()) return
    const el = ref.current
    if (el && el.innerHTML !== html) el.innerHTML = html
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [html])
}
