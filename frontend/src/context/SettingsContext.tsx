import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface SettingsContextValue {
  urgentWindowDays: number
  setUrgentWindowDays: (days: number) => void
  notifyDayBefore: boolean
  setNotifyDayBefore: (enabled: boolean) => void
}

const SettingsContext = createContext<SettingsContextValue | null>(null)

const STORAGE_KEY = 'checklist-settings'

interface StoredSettings {
  urgentWindowDays: number
  notifyDayBefore: boolean
}

function loadSettings(): StoredSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { urgentWindowDays: 0, notifyDayBefore: false }
    const parsed = JSON.parse(raw)
    return {
      urgentWindowDays: typeof parsed.urgentWindowDays === 'number' ? parsed.urgentWindowDays : 0,
      notifyDayBefore: Boolean(parsed.notifyDayBefore),
    }
  } catch {
    return { urgentWindowDays: 0, notifyDayBefore: false }
  }
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [urgentWindowDays, setUrgentWindowDays] = useState(() => loadSettings().urgentWindowDays)
  const [notifyDayBefore, setNotifyDayBefore] = useState(() => loadSettings().notifyDayBefore)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ urgentWindowDays, notifyDayBefore }))
  }, [urgentWindowDays, notifyDayBefore])

  return (
    <SettingsContext.Provider
      value={{ urgentWindowDays, setUrgentWindowDays, notifyDayBefore, setNotifyDayBefore }}
    >
      {children}
    </SettingsContext.Provider>
  )
}

export function useSettings() {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error('useSettings must be used within a SettingsProvider')
  return ctx
}
