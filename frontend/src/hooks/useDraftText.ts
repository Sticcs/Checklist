import { useEffect, useState } from 'react'

const PREFIX = 'checklist-draft:'

// Exported for components that already manage their own dirty-tracked draft
// state (the notes/pages editors - see TaskCard, SubtaskNotepad,
// AssignmentWorkspace) and just need somewhere durable to mirror it, rather
// than adopting this whole hook.
export function readDraft(key: string): string | null {
  try {
    return localStorage.getItem(PREFIX + key)
  } catch {
    return null
  }
}

export function writeDraft(key: string, value: string) {
  try {
    if (value) localStorage.setItem(PREFIX + key, value)
    else localStorage.removeItem(PREFIX + key)
  } catch {
    // Storage unavailable/full - the in-memory value still works for this
    // tab, it just won't survive a reload. Not worth surfacing to the user.
  }
}

// For fields that autosave via a debounced mutation (notes, pages) instead
// of a discrete "submit" button. Unlike readDraft/writeDraft above, an
// empty value is a legitimate saved state here (the user cleared their
// notes on purpose) - "no pending edit" has to be tracked separately from
// "the pending edit's content happens to be empty," so this wraps the value
// in a small envelope instead of using string-emptiness as the signal.
export function readPendingDraft<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(PREFIX + 'pending:' + key)
    return raw === null ? null : (JSON.parse(raw) as T)
  } catch {
    return null
  }
}

export function writePendingDraft<T>(key: string, value: T) {
  try {
    localStorage.setItem(PREFIX + 'pending:' + key, JSON.stringify(value))
  } catch {
    // Storage unavailable/full - see the note on writeDraft above.
  }
}

export function clearPendingDraft(key: string) {
  try {
    localStorage.removeItem(PREFIX + 'pending:' + key)
  } catch {
    // ignore
  }
}

// A plain useState that also mirrors itself to localStorage under `key`, so
// text typed into a box (a new task, a list item, a subtask) survives an
// accidental reload or a dropped connection instead of just vanishing - the
// single biggest source of "I typed something and it disappeared." Nothing
// here talks to the network; a component clears the draft itself (by
// setting the value back to '') once the text has actually been submitted
// or safely queued in the offline outbox.
export function useDraftText(key: string) {
  const [value, setValue] = useState(() => readDraft(key) ?? '')

  useEffect(() => {
    setValue(readDraft(key) ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(() => {
    writeDraft(key, value)
  }, [key, value])

  return [value, setValue] as const
}
