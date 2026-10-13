import type { ListEntry } from '../types'

// created_at is a UTC-offset ISO string, expires_at a naive local
// "YYYY-MM-DDTHH:MM" string (see lists_table's column comments for why they
// differ) - new Date(...) parses both into correct, directly-comparable
// absolute instants despite the differing conventions, so don't "fix" this
// into using the same format for both.
export function expiryProgressPct(list: ListEntry, nowMs: number): number | null {
  if (list.kind !== 'expiry' || !list.expires_at) return null
  const created = new Date(list.created_at).getTime()
  const expires = new Date(list.expires_at).getTime()
  if (!(expires > created)) return 0
  return Math.max(0, Math.min(100, ((expires - nowMs) / (expires - created)) * 100))
}

export function expiryGlowClass(list: ListEntry, nowMs: number): string {
  const pct = expiryProgressPct(list, nowMs)
  if (pct === null) return ''
  if (pct > 60) return 'list-glow-white'
  if (pct >= 25) return 'list-glow-yellow'
  return 'list-glow-red'
}
