import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { useLists } from '../hooks/useLists'
import { useMoveTask } from '../hooks/useTasks'

interface Props {
  taskId: number
  currentListId: number | null
}

// A "↪️" icon button + popover, matching the "⋮" popovers already used
// elsewhere (ListMenu, TaskCard's compact-view menu) - lists every other
// 'main'/'custom' list (Shopping excluded: its items are found by category
// alone, never list_id, so it was never a valid move target - see the
// backend's _require_movable_list) as a one-click move target.
export function MoveToMenu({ taskId, currentListId }: Props) {
  const { data: listsData } = useLists()
  const moveTask = useMoveTask()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [open])

  const targets = (listsData?.lists ?? []).filter(
    (l) => (l.kind === 'main' || l.kind === 'custom') && l.id !== currentListId
  )

  // Nothing to move to (only one list exists) - no point showing a button
  // that would open an empty popover.
  if (targets.length === 0) return null

  return (
    <div className="move-to-menu" ref={ref} data-focus-exempt>
      <button
        type="button"
        className="icon-btn"
        title="Move to another list"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((prev) => !prev)
        }}
      >
        ↪️
      </button>
      {open && (
        <div className="compact-menu-popover" data-focus-exempt>
          {targets.map((list) => (
            <button
              key={list.id}
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setOpen(false)
                moveTask.mutate(
                  { id: taskId, listId: list.id },
                  { onSuccess: () => toast(`📋 Moved to "${list.name}"`) }
                )
              }}
            >
              📋 {list.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
