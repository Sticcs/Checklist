import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { useOutbox } from '../hooks/useOutbox'

// The visible half of the offline-safety net (see offlineOutbox.ts /
// useOfflineSync.ts for the other half): confirms that text which failed to
// submit wasn't just lost, so a dropped connection reads as "handled" up
// front instead of leaving you to wonder after the fact.
export function OfflineBanner() {
  const online = useOnlineStatus()
  const outbox = useOutbox()

  if (online && outbox.length === 0) return null

  const pendingWord = `${outbox.length} item${outbox.length === 1 ? '' : 's'}`

  return (
    <div className={online ? 'offline-banner offline-banner-sending' : 'offline-banner'}>
      {!online &&
        (outbox.length > 0
          ? `You're offline — ${pendingWord} waiting will be sent automatically once you're back online.`
          : "You're offline — anything you add now is saved and will be sent automatically once you're back online.")}
      {online && `Sending ${pendingWord}…`}
    </div>
  )
}
