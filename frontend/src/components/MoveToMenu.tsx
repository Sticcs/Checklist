import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
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
//
// The popover is portaled into <body>, not just position:absolute inside
// this button's own wrapper - when this renders in TaskCard's non-compact
// reveal row, that row (.task-reveal) is overflow:hidden for its own open/
// close height animation, which silently clipped an absolutely-positioned
// popover anchored inside it (it "worked" - the click landed and moved the
// task - but the popover itself was invisible). Positioning it via the
// button's own screen coordinates instead sidesteps any ancestor's
// overflow/clipping entirely, in every context this component is used.
export function MoveToMenu({ taskId, currentListId }: Props) {
  const { data: listsData } = useLists()
  const moveTask = useMoveTask()
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null)
  const btnRef = useRef<HTMLButtonElement>(null)

  // Closing on scroll/resize (rather than continuously tracking position) -
  // simplest way to avoid the portaled popover drifting away from a button
  // whose scrolling ancestor just moved out from under it. capture:true
  // catches scroll from any scrollable ancestor, not just the window.
  useEffect(() => {
    if (!open) return
    const close = () => setOpen(false)
    document.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      document.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [open])

  const targets = (listsData?.lists ?? []).filter(
    (l) => (l.kind === 'main' || l.kind === 'custom') && l.id !== currentListId
  )

  // Nothing to move to (only one list exists) - no point showing a button
  // that would open an empty popover.
  if (targets.length === 0) return null

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="icon-btn"
        title="Move to another list"
        onClick={(e) => {
          e.stopPropagation()
          const rect = btnRef.current?.getBoundingClientRect()
          if (rect) setPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right })
          setOpen((prev) => !prev)
        }}
      >
        ↪️
      </button>
      {open &&
        pos &&
        createPortal(
          // A full-screen, invisible click-catcher (same pattern as
          // AddTaskForm's TaskEntryVignetteOverlay) - closes only when the
          // click lands on the backdrop itself, not any descendant, so
          // clicking a list button here doesn't also trigger this close.
          <div
            className="move-to-backdrop"
            onClick={(e) => {
              if (e.target === e.currentTarget) setOpen(false)
            }}
          >
            <div
              className="compact-menu-popover move-to-popover"
              style={{ top: pos.top, right: pos.right }}
              data-focus-exempt
            >
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
          </div>,
          document.body
        )}
    </>
  )
}
