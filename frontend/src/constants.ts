export const CATEGORIES = ['House', 'Work', 'Study', 'Personal', 'Assessment', 'Shopping', 'Custom'] as const
export const PRIORITIES = ['High', 'Medium', 'Low'] as const

export const CAT_KEYS: Record<string, string> = {
  House: 'H',
  Work: 'W',
  Study: 'S',
  Personal: 'P',
  Assessment: 'A',
  Shopping: 'G',
  Custom: 'C',
}
export const PRI_KEYS: Record<string, string> = { High: 'T', Medium: 'M', Low: 'L' }

export const PRIORITY_ORDER: Record<string, number> = { High: 0, Medium: 1, Low: 2 }

// Tasks created with this category are routed into the separate Assessments
// panel instead of the main task list (see TaskListPage) - everything else
// about them (mutations, undo/redo, clear completed) is shared with normal
// tasks, only the UI they render into and the fields they expose differ.
export const ASSESSMENT_CATEGORY = 'Assessment'

// Same routing idea as ASSESSMENT_CATEGORY, into the Shopping panel instead
// (see TaskListPage's entryTab). Picking this category in AddTaskForm skips
// the priority/due-date steps entirely (see its Shopping fast-path) - a
// shopping item doesn't need either, it's just a checkable line.
export const SHOPPING_CATEGORY = 'Shopping'

// Purely for DB self-description on tasks created via a custom list's own
// add-item box (see ListPanel) - the actual routing/exclusion logic (which
// list a task belongs to, and keeping it out of the main task list) is
// driven by the task's `list_id` field, not this category string.
export const LIST_ITEM_CATEGORY = 'List'

// The one real deployment of this app - used only by the desktop app's
// "Sign in with Google" link (AuthPage), which must hit the actual live
// backend even from inside the otherwise fully-offline desktop app, since
// that's what makes the same Google account show the same tasks on both.
// See backend/app/config.py's public_base_url for the matching backend value.
export const PRODUCTION_URL = 'https://checklist-kmtw.onrender.com'

// sessionStorage key holding a share link's token captured pre-auth (see
// main.tsx's bootstrap, which runs before React mounts) - read once by
// TaskListPage's pending-join effect right after login/signup/guest-continue
// lands. Lives here (not main.tsx) so both can import it without a circular
// dependency (main.tsx -> App.tsx -> ... -> TaskListPage.tsx -> main.tsx).
export const PENDING_JOIN_TOKEN_KEY = 'checklist-pending-join-token'
