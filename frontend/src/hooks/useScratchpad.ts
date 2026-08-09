import { useEffect, useState } from 'react'

const STORAGE_PREFIX = 'checklist-scratchpad:'

// Local-only, per-username, not synced to the backend - this is meant as a
// throwaway scratch space, not another persisted data model to migrate.
export function useScratchpad(username: string | undefined) {
  const key = `${STORAGE_PREFIX}${username ?? 'anon'}`
  const [text, setText] = useState(() => localStorage.getItem(key) ?? '')

  useEffect(() => {
    setText(localStorage.getItem(key) ?? '')
  }, [key])

  useEffect(() => {
    if (text) localStorage.setItem(key, text)
    else localStorage.removeItem(key)
  }, [key, text])

  return [text, setText] as const
}
