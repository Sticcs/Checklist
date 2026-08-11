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

// The one real deployment of this app - used only by the desktop app's
// "Sign in with Google" link (AuthPage), which must hit the actual live
// backend even from inside the otherwise fully-offline desktop app, since
// that's what makes the same Google account show the same tasks on both.
// See backend/app/config.py's public_base_url for the matching backend value.
export const PRODUCTION_URL = 'https://checklist-kmtw.onrender.com'
