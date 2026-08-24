import { useEffect, useState } from 'react'

// Matches index.css's own `@media (max-width: 900px)` breakpoint - kept as
// a single source of truth here so TaskListPage can pick which way to
// animate the sidebar (width, side-by-side on desktop; height, an
// expanding panel on narrow/portrait screens - see its own comment) instead
// of that decision drifting out of sync with the stylesheet's breakpoint.
const QUERY = '(max-width: 900px)'

export function useIsMobileLayout(): boolean {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(QUERY).matches
  )

  useEffect(() => {
    const mql = window.matchMedia(QUERY)
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])

  return isMobile
}
