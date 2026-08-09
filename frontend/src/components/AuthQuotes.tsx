import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

const QUOTES = [
  'One task closer.',
  'Small steps, done consistently.',
  'Clarity beats chaos.',
  'Check it off.',
  'Progress, not perfection.',
  'Nothing forgotten.',
  'Plan it. Do it. Done.',
  'Every list starts with one line.',
]

// All web-safe and all still comfortably readable at this size - no script
// or decorative faces, since the point is variety, not a readability tax.
const FONTS = [
  "Georgia, 'Times New Roman', serif",
  "'Trebuchet MS', 'Segoe UI', sans-serif",
  "'Courier New', Courier, monospace",
  "Palatino, 'Palatino Linotype', serif",
  "Verdana, Geneva, sans-serif",
  "'Century Gothic', 'Futura', sans-serif",
  "Garamond, Baskerville, serif",
]

function pickNext<T>(list: T[], exclude: T): T {
  let next = exclude
  while (next === exclude) {
    next = list[Math.floor(Math.random() * list.length)]
  }
  return next
}

// One large quote above the auth card, cycling on its own randomized 3-5s
// interval - each change swaps both the phrase and its font together so it
// reads as a single deliberate change instead of two things flickering
// independently.
export function AuthQuotes() {
  const [quote, setQuote] = useState(() => QUOTES[Math.floor(Math.random() * QUOTES.length)])
  const [font, setFont] = useState(() => FONTS[Math.floor(Math.random() * FONTS.length)])

  useEffect(() => {
    let cancelled = false
    let handle: ReturnType<typeof setTimeout>

    const tick = () => {
      const delay = 3000 + Math.random() * 2000
      handle = setTimeout(() => {
        if (cancelled) return
        setQuote((prev) => pickNext(QUOTES, prev))
        setFont((prev) => pickNext(FONTS, prev))
        tick()
      }, delay)
    }
    tick()

    return () => {
      cancelled = true
      clearTimeout(handle)
    }
  }, [])

  return (
    <div className="auth-quote-main">
      <AnimatePresence mode="wait">
        <motion.p
          key={quote}
          style={{ fontFamily: font }}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.5 }}
        >
          {quote}
        </motion.p>
      </AnimatePresence>
    </div>
  )
}
