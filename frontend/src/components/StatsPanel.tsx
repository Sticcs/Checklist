import { useStats } from '../hooks/useStats'
import { CollapsibleSection } from './CollapsibleSection'

interface Props {
  open: boolean
  onToggle: (open: boolean) => void
}

function heatClass(count: number): string {
  if (count === 0) return 'stats-heat-cell heat-0'
  if (count === 1) return 'stats-heat-cell heat-1'
  if (count === 2) return 'stats-heat-cell heat-2'
  return 'stats-heat-cell heat-3'
}

export function StatsPanel({ open, onToggle }: Props) {
  const stats = useStats(open)

  return (
    <CollapsibleSection title="📊 Stats" open={open} onToggle={onToggle}>
      {stats.data && (
        <div className="stats-body">
          <div className="stats-row">
            <div className="stat-block">
              <span className="stat-value">🔥 {stats.data.current_streak}</span>
              <span className="stat-label">Streak</span>
            </div>
            <div className="stat-block">
              <span className="stat-value">🏆 {stats.data.longest_streak}</span>
              <span className="stat-label">Best streak</span>
            </div>
            <div className="stat-block">
              <span className="stat-value">{stats.data.completed_today}</span>
              <span className="stat-label">Today</span>
            </div>
            <div className="stat-block">
              <span className="stat-value">{stats.data.completed_this_week}</span>
              <span className="stat-label">This week</span>
            </div>
          </div>
          <div className="stats-heatmap" title="Completions over the last 30 days">
            {stats.data.daily_counts.map((d) => (
              <span key={d.date} className={heatClass(d.count)} title={`${d.date}: ${d.count} completed`} />
            ))}
          </div>
        </div>
      )}
    </CollapsibleSection>
  )
}
