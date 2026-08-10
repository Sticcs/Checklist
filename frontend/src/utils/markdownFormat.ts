export type FormatKind = 'bold' | 'italic' | 'underline'

// Markdown has no native underline, so <u> is the standard workaround most
// markdown-adjacent editors reach for with Ctrl+U.
const WRAPPERS: Record<FormatKind, [string, string]> = {
  bold: ['**', '**'],
  italic: ['*', '*'],
  underline: ['<u>', '</u>'],
}

export interface FormatResult {
  value: string
  selectionStart: number
  selectionEnd: number
}

// Wraps the current selection in the given format's markers - or, if the
// selection is already exactly wrapped in them, strips the markers back off
// (so the same shortcut/button toggles the format rather than only ever
// adding more markers). An empty (collapsed) selection just inserts an empty
// pair of markers with the cursor left in between, ready to type into.
export function toggleMarkdownFormat(el: HTMLTextAreaElement, kind: FormatKind): FormatResult {
  const [open, close] = WRAPPERS[kind]
  const { value, selectionStart: start, selectionEnd: end } = el
  const selected = value.slice(start, end)

  const isWrapped = selected.length >= open.length + close.length && selected.startsWith(open) && selected.endsWith(close)

  if (isWrapped) {
    const inner = selected.slice(open.length, selected.length - close.length)
    return {
      value: value.slice(0, start) + inner + value.slice(end),
      selectionStart: start,
      selectionEnd: start + inner.length,
    }
  }

  if (selected.length === 0) {
    return {
      value: value.slice(0, start) + open + close + value.slice(end),
      selectionStart: start + open.length,
      selectionEnd: start + open.length,
    }
  }

  // Select the *whole* wrapped span, markers included (not just the inner
  // text) - so a repeat click/shortcut on this same selection lands on the
  // isWrapped branch above and toggles the format back off, instead of
  // wrapping it a second time.
  return {
    value: value.slice(0, start) + open + selected + close + value.slice(end),
    selectionStart: start,
    selectionEnd: start + open.length + selected.length + close.length,
  }
}
