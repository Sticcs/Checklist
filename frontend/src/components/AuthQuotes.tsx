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

const POSITIONS = ['auth-quote-tl', 'auth-quote-br', 'auth-quote-tr']

function randomQuote(exclude: string): string {
  let next = exclude
  while (next === exclude) {
    next = QUOTES[Math.floor(Math.random() * QUOTES.length)]
  }
  return next
}

// One independently-cycling quote per screen corner - each on its own
// randomized 3-5s interval (rather than a shared timer) so they drift out of
// sync instead of changing in unison, which read as more "alive."
function FloatingQuote({ position }: { position: string }) {
  const [quote, setQuote] = useState(() => QUOTES[Math.floor(Math.random() * QUOTES.length)])

  useEffect(() => {
    let cancelled = false
    let handle: ReturnType<typeof setTimeout>

    const tick = () => {
      const delay = 3000 + Math.random() * 2000
      handle = setTimeout(() => {
        if (cancelled) return
        setQuote((prev) => randomQuote(prev))
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
    <div className={`auth-quote ${position}`}>
      <AnimatePresence mode="wait">
        <motion.span
          key={quote}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.6 }}
        >
          {quote}
        </motion.span>
      </AnimatePresence>
    </div>
  )
}

export function AuthQuotes() {
  return (
    <>
      {POSITIONS.map((position) => (
        <FloatingQuote key={position} position={position} />
      ))}
    </>
  )
}
