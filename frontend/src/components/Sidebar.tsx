import { useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useSettings } from '../context/SettingsContext'
import { useFormattingContext } from '../context/FormattingContext'
import { useActivity } from '../hooks/useActivity'
import { useClearAll, useClearCompleted, useMarkAllCompleted } from '../hooks/useTasks'
import { useUndo, useRedo } from '../hooks/useUndoRedo'
import { useWallpaper } from '../hooks/useWallpaper'
import { resizeImageToDataUrl } from '../utils/resizeImage'
import { StatsPanel } from './StatsPanel'
import { CollapsibleSection } from './CollapsibleSection'
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
  hasCompletedTasks: boolean
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
  hasCompletedTasks,
  onClose,
}: Props) {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const { urgentWindowDays, setUrgentWindowDays, notifyDayBefore, setNotifyDayBefore } = useSettings()
  const [activityOpen, setActivityOpen] = useState(false)
  const [statsOpen, setStatsOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [wallpaper, setWallpaper] = useWallpaper(user?.username)
  const wallpaperInputRef = useRef<HTMLInputElement>(null)

  const handleNotifyToggle = async (checked: boolean) => {
    if (checked && typeof Notification !== 'undefined' && Notification.permission === 'default') {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') return
    }
    setNotifyDayBefore(checked)
  }

  const { active: formattingActive, applyFormat } = useFormattingContext()
  const undo = useUndo()
  const redo = useRedo()
  const markAllCompleted = useMarkAllCompleted()
  const clearCompleted = useClearCompleted()
  const clearAll = useClearAll()
  const activity = useActivity(activityOpen)

  const handleWallpaperFile = async (file: File | undefined) => {
    if (!file) return
    const dataUrl = await resizeImageToDataUrl(file)
    setWallpaper(dataUrl)
  }

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
            <button
              type="button"
              className="icon-btn"
              onClick={() => wallpaperInputRef.current?.click()}
              title="Set a custom wallpaper (saved on this device only)"
            >
              🖼️
            </button>
            {wallpaper && (
              <button type="button" className="icon-btn" onClick={() => setWallpaper(null)} title="Reset wallpaper">
                ↺
              </button>
            )}
            <input
              ref={wallpaperInputRef}
              type="file"
              accept="image/*"
              className="wallpaper-file-input"
              onChange={(e) => {
                void handleWallpaperFile(e.target.files?.[0])
                e.target.value = ''
              }}
            />
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
            <option>Manual</option>
          </select>
        </label>
      </div>

      <hr />

      <div className="sidebar-format-row">
        {(
          [
            ['bold', 'Bold (Ctrl+B)', <b key="b">B</b>],
            ['italic', 'Italic (Ctrl+I)', <i key="i">I</i>],
            ['underline', 'Underline (Ctrl+U)', <u key="u">U</u>],
          ] as const
        ).map(([kind, title, glyph]) => (
          <button
            key={kind}
            type="button"
            className={formattingActive ? 'icon-btn btn-primary' : 'icon-btn'}
            disabled={!formattingActive}
            title={title}
            // Keeps focus (and the selection) in whichever textarea is
            // active instead of moving it to this button, which is what a
            // plain click would do - applyFormat needs that selection intact.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => applyFormat(kind)}
          >
            {glyph}
          </button>
        ))}
      </div>

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
        <button
          type="button"
          className={hasCompletedTasks ? 'btn-secondary btn-block glow-eligible' : 'btn-secondary btn-block'}
          onClick={() => clearCompleted.mutate()}
        >
          Clear completed
        </button>
        <button type="button" className="btn-secondary btn-block" onClick={() => clearAll.mutate()}>
          Clear all
        </button>
      </div>

      <hr />

      <StatsPanel open={statsOpen} onToggle={setStatsOpen} />

      <CollapsibleSection title="Activity Logs" open={activityOpen} onToggle={setActivityOpen}>
        <div className="activity-log">
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
        </div>
      </CollapsibleSection>

      <CollapsibleSection title="⚙️ Settings" open={settingsOpen} onToggle={setSettingsOpen}>
        <div className="settings-body">
          <label className="settings-field">
            Mark tasks 🚨 urgent within
            <input
              type="number"
              min={0}
              max={30}
              value={urgentWindowDays}
              onChange={(e) => setUrgentWindowDays(Math.max(0, Number(e.target.value) || 0))}
              className="settings-number-input"
            />
            day(s) of their due date
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={notifyDayBefore}
              onChange={(e) => void handleNotifyToggle(e.target.checked)}
            />
            🔔 Notify me the day before something's due
          </label>
        </div>
      </CollapsibleSection>

      <p className="sidebar-credits">
        Vibecoded with Claude. Made by Debayan Mukherjee. Found a bug? DM{' '}
        <a href="https://www.instagram.com/debayanm_/" target="_blank" rel="noopener noreferrer">
          @debayanm_
        </a>
        .{' '}
        <a href="https://github.com/Sticcs/Checklist" target="_blank" rel="noopener noreferrer">
          GitHub
        </a>
      </p>
    </aside>
  )
}
