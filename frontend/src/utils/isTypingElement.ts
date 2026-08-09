// A focused checkbox/radio still has tagName === 'INPUT', but it doesn't
// consume typed characters the way a text input does - treating it as
// "typing" would make hotkeys silently no-op any time focus is left on a
// checkbox (e.g. after clicking a filter) instead of on actual body text.
const NON_TEXT_INPUT_TYPES = new Set(['checkbox', 'radio', 'button', 'submit', 'range', 'color'])

export function isTypingElement(el: Element | null): boolean {
  if (!el) return false
  if (el.tagName === 'TEXTAREA') return true
  if (el.tagName === 'INPUT') {
    const type = (el as HTMLInputElement).type
    return !NON_TEXT_INPUT_TYPES.has(type)
  }
  return false
}
