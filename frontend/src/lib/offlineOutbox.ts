// A tiny persisted queue of "add" submissions that failed because the
// device was offline, not because the server actually rejected them (see
// useAddTask/useAddSubtask's onError, the only places that add to this).
// Kept in localStorage (not just React state) so a reload while still
// offline doesn't lose track of what's still waiting to be sent - the whole
// point is that this survives the exact situation that caused it.
export type OutboxEntry =
  | {
      id: string
      kind: 'task'
      label: string
      createdAt: number
      payload: { text: string; priority: string; category: string; dueDate: string | null; listId?: number | null }
    }
  | {
      id: string
      kind: 'subtask'
      label: string
      createdAt: number
      payload: { taskId: number; text: string }
    }

const STORAGE_KEY = 'checklist-offline-outbox'
const listeners = new Set<() => void>()

function notify() {
  listeners.forEach((l) => l())
}

export function getOutbox(): OutboxEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as OutboxEntry[]) : []
  } catch {
    return []
  }
}

function setOutbox(entries: OutboxEntry[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // Storage unavailable/full - the entry still lives in memory for this
    // tab via the listener-driven React state, it just won't survive reload.
  }
  notify()
}

export function addToOutbox(entry: Omit<OutboxEntry, 'id' | 'createdAt'>) {
  const full = { ...entry, id: crypto.randomUUID(), createdAt: Date.now() } as OutboxEntry
  setOutbox([...getOutbox(), full])
  return full
}

export function removeFromOutbox(id: string) {
  setOutbox(getOutbox().filter((e) => e.id !== id))
}

export function subscribeOutbox(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
