import { useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { useScratchpad } from '../hooks/useScratchpad'
import { isTypingElement } from '../utils/isTypingElement'

export function Scratchpad() {
  const { user } = useAuth()
  const [text, setText] = useScratchpad(user?.username)
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== '`') return
      if (isTypingElement(document.activeElement)) return
      e.preventDefault()
      ref.current?.focus()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  return (
    <div className="scratchpad">
      <textarea
        ref={ref}
        className="scratchpad-input"
        placeholder="Scratchpad... (press ` to focus)"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </div>
  )
}
