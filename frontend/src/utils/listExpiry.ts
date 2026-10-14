import type { ListEntry } from '../types'

// cycle_started_at is a UTC-offset ISO string, expires_at a naive local
// "YYYY-MM-DDTHH:MM" string (see lists_table's column comments for why they
// differ) - new Date(...) parses both into correct, directly-comparable
// absolute instants despite the differing conventions, so don't "fix" this
// into using the same format for both.
//
// Uses cycle_started_at, not created_at - the countdown's "start" resets
// every time the list is "Continued" (see ContinueExpiryButton), so a list
// that's existed for days but was just continued with a fresh one-day
// extension reads as freshly-started (white), not nearly-expired (red)
// against its whole multi-day history. Falls back to created_at for any
// list fetched before that column existed server-side.
export function expiryProgressPct(list: ListEntry, nowMs: number): number | null {
  if (list.kind !== 'expiry' || !list.expires_at) return null
  const created = new Date(list.cycle_started_at ?? list.created_at).getTime()
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

// Raw ms remaining, clamped at 0 - unlike expiryProgressPct this isn't a
// percentage, it's what the live countdown (see ExpiryTimer) actually
// counts down.
export function expiryRemainingMs(list: ListEntry, nowMs: number): number | null {
  if (list.kind !== 'expiry' || !list.expires_at) return null
  return Math.max(0, new Date(list.expires_at).getTime() - nowMs)
}

// "1d 4h", "2h 15m", "45m 12s", "30s" - drops to the next-finer unit once
// the coarser one hits zero, never shows more than two units at once (a
// countdown reading "1d 4h 32m 11s" is harder to read at a glance, not
// more useful).
export function formatRemaining(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

// Mirrors expiryGlowClass's buckets, plus a distinct message once the
// deadline has actually passed (as opposed to just being deep in the red
// zone) - the glow itself doesn't need that extra distinction, but the
// text reads oddly saying "almost done" about a deadline that's already
// gone.
export function expiryProgressMessage(list: ListEntry, nowMs: number): string {
  const remaining = expiryRemainingMs(list, nowMs)
  if (remaining === null) return ''
  if (remaining <= 0) return "Time's up!"
  const pct = expiryProgressPct(list, nowMs)
  if (pct === null) return ''
  if (pct > 60) return 'Still a while to go'
  if (pct >= 25) return 'Getting closer...'
  return 'Almost done!'
}
