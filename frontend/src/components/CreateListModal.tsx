import { useState } from 'react'
import type { ListEntry } from '../types'
import { useCreateList } from '../hooks/useLists'
import { toISODate } from '../utils/dueDatePresets'
import { VignetteOverlay } from './VignetteOverlay'

interface Props {
  onCreated: (list: ListEntry) => void
  onCancel: () => void
}

// Step 1 of "+": pick a regular checklist (created immediately, same as
// the old one-click "+") or an expiry checklist, which needs one more step
// to collect its deadline before anything is created.
export function CreateListModal({ onCreated, onCancel }: Props) {
  const createList = useCreateList()
  const [step, setStep] = useState<'choose' | 'expiry-time'>('choose')
  const [expiresAt, setExpiresAt] = useState(() => `${toISODate(new Date())}T23:59`)

  const createRegular = () => {
    createList.mutate({ kind: 'custom' }, { onSuccess: onCreated })
  }

  const createExpiry = () => {
    if (!expiresAt) return
    createList.mutate({ kind: 'expiry', expiresAt }, { onSuccess: onCreated })
  }

  return (
    <VignetteOverlay onCancel={onCancel}>
      {step === 'choose' ? (
        <div className="option-row">
          <div className="option-row-header">
            <p className="option-row-label">New checklist</p>
          </div>
          <div className="option-row-buttons">
            <button type="button" className="btn-option" onClick={createRegular} disabled={createList.isPending}>
              📋 Regular checklist
            </button>
            <button type="button" className="btn-option" onClick={() => setStep('expiry-time')}>
              ⏳ Expiry checklist
            </button>
          </div>
        </div>
      ) : (
        <div className="option-row">
          <div className="option-row-header">
            <button type="button" className="option-row-back-btn" title="Back" onClick={() => setStep('choose')}>
              ‹
            </button>
            <p className="option-row-label">Expires at</p>
          </div>
          <input
            type="datetime-local"
            className="custom-input"
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            autoFocus
          />
          <div className="option-row-buttons">
            <button type="button" className="btn-primary" onClick={createExpiry} disabled={createList.isPending}>
              Create
            </button>
          </div>
        </div>
      )}
    </VignetteOverlay>
  )
}
