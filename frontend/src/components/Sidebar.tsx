import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useActivity } from '../hooks/useActivity'
import { useClearAll, useClearCompleted, useMarkAllCompleted } from '../hooks/useTasks'
import { useUndo, useRedo } from '../hooks/useUndoRedo'
import type { SortBy } from '../utils/sortTasks'

export type StatusFilter = 'All' | 'Active' | 'Completed'

interface Props {
  search: string
  onSearchChange: (v: string) => void
  statusFilter: StatusFilter
  onStatusFilterChange: (v: StatusFilter) => void
  availableCategories: string[]
  categoryFilter: string[]
  onCategoryFilterChange: (v: string[]) => void
  pinnedOnly: boolean
  onPinnedOnlyChange: (v: boolean) => void
  sortBy: SortBy
  onSortByChange: (v: SortBy) => void
  canUndo: boolean
  canRedo: boolean
  onClose: () => void
}

const ACTIVITY_META: Record<string, { icon: string; label: string }> = {
  added: { icon: '➕', label: 'Added' },
  completed: { icon: '✅', label: 'Completed' },
  uncompleted: { icon: '↩️', label: 'Unmarked' },
  pinned: { icon: '📌', label: 'Pinned' },
  unpinned: { icon: '📌', label: 'Unpinned' },
  deleted: { icon: '🗑️', label: 'Deleted' },
  edited: { icon: '✏️', label: 'Edited' },
  cleared_completed: { icon: '🧹', label: 'Cleared completed' },
  cleared_all: { icon: '🗑️', label: 'Cleared all' },
  marked_all_completed: { icon: '✅', label: 'Marked all completed' },
}

export function Sidebar({
  search,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  availableCategories,
  categoryFilter,
  onCategoryFilterChange,
  pinnedOnly,
  onPinnedOnlyChange,
  sortBy,
  onSortByChange,
  canUndo,
  canRedo,
  onClose,
}: Props) {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [activityOpen, setActivityOpen] = useState(false)

  const undo = useUndo()
  const redo = useRedo()
  const markAllCompleted = useMarkAllCompleted()
  const clearCompleted = useClearCompleted()
  const clearAll = useClearAll()
  const activity = useActivity(activityOpen)

  const toggleCategory = (cat: string) => {
    onCategoryFilterChange(
      categoryFilter.includes(cat) ? categoryFilter.filter((c) => c !== cat) : [...categoryFilter, cat]
    )
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-profile">
          <div className="profile-indicator">
            <span className="profile-avatar">👤</span>
            {user?.is_guest ? 'Guest' : user?.username}
          </div>
          {user?.is_guest && <p className="guest-note">Tasks won't be saved after you sign out</p>}
          <div className="sidebar-profile-actions">
            <button type="button" className="btn-secondary" onClick={() => logout()}>
              Sign out
            </button>
            <button type="button" className="icon-btn theme-toggle" onClick={toggleTheme} title="Toggle theme">
              {theme === 'light' ? '🌙' : '☀️'}
            </button>
          </div>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} title="Close sidebar">
          ✕
        </button>
      </div>

      <hr />

      <div className="sidebar-filters">
        <h3 className="sidebar-heading">Filters</h3>
        <input
          className="search-input"
          placeholder="Search tasks..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <div className="status-filter-row">
          {(['All', 'Active', 'Completed'] as const).map((s) => (
            <label key={s} className="radio-label">
              <input
                type="radio"
                name="status-filter"
                checked={statusFilter === s}
                onChange={() => onStatusFilterChange(s)}
              />
              {s}
            </label>
          ))}
        </div>
        <label className="checkbox-label">
          <input type="checkbox" checked={pinnedOnly} onChange={(e) => onPinnedOnlyChange(e.target.checked)} />
          📌 Pinned only
        </label>

        {availableCategories.length > 0 && (
          <div className="category-filter">
            <p className="sidebar-subheading">Category</p>
            {availableCategories.map((cat) => (
              <label key={cat} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={categoryFilter.includes(cat)}
                  onChange={() => toggleCategory(cat)}
                />
                {cat}
              </label>
            ))}
          </div>
        )}

        <label className="sort-select">
          Sort by
          <select value={sortBy} onChange={(e) => onSortByChange(e.target.value as SortBy)}>
            <option>Priority</option>
            <option>Due date</option>
            <option>Newest first</option>
          </select>
        </label>
      </div>

      <hr />

      <div className="sidebar-undo-redo">
        <button type="button" className="btn-secondary" disabled={!canUndo} onClick={() => undo.mutate()}>
          ↩️ Undo
        </button>
        <button type="button" className="btn-secondary" disabled={!canRedo} onClick={() => redo.mutate()}>
          ↪️ Redo
        </button>
      </div>

      <div className="sidebar-bulk-actions">
        <button type="button" className="btn-secondary btn-block" onClick={() => markAllCompleted.mutate()}>
          Mark all completed
        </button>
        <button type="button" className="btn-secondary btn-block" onClick={() => clearCompleted.mutate()}>
          Clear completed
        </button>
        <button type="button" className="btn-secondary btn-block" onClick={() => clearAll.mutate()}>
          Clear all
        </button>
      </div>

      <hr />

      <details
        className="activity-log"
        open={activityOpen}
        onToggle={(e) => setActivityOpen(e.currentTarget.open)}
      >
        <summary>Activity Logs</summary>
        {activity.data && activity.data.length === 0 && <p>No recent activity.</p>}
        <ul>
          {activity.data?.map((entry) => {
            const meta = ACTIVITY_META[entry.action] ?? { icon: '•', label: entry.action }
            const when = new Date(entry.created_at)
            return (
              <li key={entry.id} className="activity-log-entry">
                <span>
                  {meta.icon} <b>{meta.label}:</b> {entry.detail}
                </span>
                <span className="activity-log-time">{when.toLocaleString()}</span>
              </li>
            )
          })}
        </ul>
      </details>
    </aside>
  )
}
