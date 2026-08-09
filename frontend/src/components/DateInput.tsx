import { useRef } from 'react'

interface Props {
  value: string
  onCommit: (value: string) => void
  onEnter?: (value: string) => void
  className?: string
  autoFocus?: boolean
}

// A native <input type="date"> deliberately kept *uncontrolled* while the
// user is typing. Chromium commits a date the moment the year segment holds
// any digit - typing a single "2" after a valid month/day reports the whole
// field as complete with a zero-padded year (e.g. "0002-12-08"). Binding
// `value` to React state and feeding that back in on every keystroke (the
// previous approach) forced the DOM to that bogus intermediate value mid-
// edit, which reads as the field "resetting" and kicking you out while
// you're still typing the year. Reading the DOM's value only once, on blur
// or Enter, sidesteps the whole class of premature-commit quirks - the
// browser's own segment editing always resolves to the correct final date.
export function DateInput({ value, onCommit, onEnter, className, autoFocus }: Props) {
  // Enter commits explicitly and then blurs itself to close/deselect - that
  // synthetic blur would otherwise re-fire onBlur's own commit a beat later
  // with the same value. Harmless (idempotent) but redundant; this flag just
  // skips the second one.
  const committedRef = useRef(false)

  return (
    <input
      type="date"
      className={className}
      defaultValue={value}
      autoFocus={autoFocus}
      onBlur={(e) => {
        if (committedRef.current) return
        onCommit(e.target.value)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          const next = e.currentTarget.value
          committedRef.current = true
          onCommit(next)
          onEnter?.(next)
          e.currentTarget.blur()
        } else if (e.key === 'Escape') {
          e.preventDefault()
          e.currentTarget.blur()
        }
      }}
    />
  )
}
