export const CATEGORIES = ['House', 'Work', 'Study', 'Personal', 'Custom'] as const
export const PRIORITIES = ['High', 'Medium', 'Low'] as const

export const CAT_KEYS: Record<string, string> = { House: 'H', Work: 'W', Study: 'S', Personal: 'P', Custom: 'C' }
export const PRI_KEYS: Record<string, string> = { High: 'T', Medium: 'M', Low: 'L' }

export const PRIORITY_ORDER: Record<string, number> = { High: 0, Medium: 1, Low: 2 }
