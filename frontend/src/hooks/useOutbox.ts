import { useEffect, useState } from 'react'
import { getOutbox, subscribeOutbox, type OutboxEntry } from '../lib/offlineOutbox'

export function useOutbox(): OutboxEntry[] {
  const [entries, setEntries] = useState(getOutbox)

  useEffect(() => subscribeOutbox(() => setEntries(getOutbox())), [])

  return entries
}
