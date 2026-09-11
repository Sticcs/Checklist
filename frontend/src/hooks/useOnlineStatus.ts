import { useEffect, useState } from 'react'

// navigator.onLine only reflects whether the network interface is up, not
// whether the API is actually reachable - but it's what the 'online'/
// 'offline' events are keyed on, and it's the same signal every browser
// already uses to decide when to retry itself, so it's a reasonable proxy
// for "worth trying the outbox again."
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine)

  useEffect(() => {
    const goOnline = () => setOnline(true)
    const goOffline = () => setOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  return online
}
