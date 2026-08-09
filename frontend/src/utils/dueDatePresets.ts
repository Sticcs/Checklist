// Direct port of main.py's DUE_PRESETS, but computed from the browser's own
// local clock instead of a hardcoded server-side timezone offset (main.py
// hardcoded LOCAL_TZ = UTC+10 specifically because the Streamlit server has
// no way to know the browser's timezone - a problem that doesn't exist here,
// since `new Date()` is already local).

export type DuePreset = 'Today' | 'Tomorrow' | 'This week' | 'Next week' | 'Custom' | 'No date'

export const DUE_PRESET_ORDER: DuePreset[] = [
  'Today',
  'Tomorrow',
  'This week',
  'Next week',
  'Custom',
  'No date',
]

export function toISODate(d: Date): string {
  // yyyy-mm-dd in local time - not toISOString(), which converts to UTC
  // first and can shift the date by a day near midnight.
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function addDays(d: Date, days: number): Date {
  const copy = new Date(d)
  copy.setDate(copy.getDate() + days)
  return copy
}

function endOfWeek(d: Date): Date {
  // JS getDay(): Sun=0..Sat=6. Days remaining until (and including) Sunday.
  const daysUntilSunday = (7 - d.getDay()) % 7
  return addDays(d, daysUntilSunday)
}

export function computeDueDate(preset: DuePreset, customDate: string | null = null): string | null {
  const today = new Date()
  switch (preset) {
    case 'Today':
      return toISODate(today)
    case 'Tomorrow':
      return toISODate(addDays(today, 1))
    case 'This week':
      return toISODate(endOfWeek(today))
    case 'Next week':
      return toISODate(addDays(endOfWeek(today), 7))
    case 'Custom':
      return customDate
    case 'No date':
      return null
  }
}
