export const CATEGORIES = ['House', 'Work', 'Study', 'Personal', 'Assessment', 'Custom'] as const
export const PRIORITIES = ['High', 'Medium', 'Low'] as const

export const CAT_KEYS: Record<string, string> = {
  House: 'H',
  Work: 'W',
  Study: 'S',
  Personal: 'P',
  Assessment: 'A',
  Custom: 'C',
}
export const PRI_KEYS: Record<string, string> = { High: 'T', Medium: 'M', Low: 'L' }

export const PRIORITY_ORDER: Record<string, number> = { High: 0, Medium: 1, Low: 2 }

// Tasks created with this category are routed into the separate Assessments
// panel instead of the main task list (see TaskListPage) - everything else
// about them (mutations, undo/redo, clear completed) is shared with normal
// tasks, only the UI they render into and the fields they expose differ.
export const ASSESSMENT_CATEGORY = 'Assessment'
