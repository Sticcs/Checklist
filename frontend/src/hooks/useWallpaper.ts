import { useEffect, useState } from 'react'
import { toast } from 'sonner'

const STORAGE_PREFIX = 'checklist-wallpaper:'

// Local-only, per-username, never sent to the backend - a custom wallpaper
// is a per-device preference, not app data worth a server round trip or a
// migration. Applied by overriding the --bg-image custom property directly
// on <body> (the theme CSS only sets a *default* for that property, so an
// inline override here always wins without touching the stylesheet).
export function useWallpaper(username: string | undefined) {
  const key = `${STORAGE_PREFIX}${username ?? 'anon'}`
  const [wallpaper, setWallpaperState] = useState<string | null>(() => localStorage.getItem(key))

  useEffect(() => {
    setWallpaperState(localStorage.getItem(key))
  }, [key])

  useEffect(() => {
    if (wallpaper) {
      document.body.style.setProperty('--bg-image', `url(${wallpaper})`)
    } else {
      document.body.style.removeProperty('--bg-image')
    }
  }, [wallpaper])

  const setWallpaper = (dataUrl: string | null) => {
    try {
      if (dataUrl) localStorage.setItem(key, dataUrl)
      else localStorage.removeItem(key)
      setWallpaperState(dataUrl)
    } catch {
      toast.error('Image too large to save locally - try a smaller one')
    }
  }

  return [wallpaper, setWallpaper] as const
}
