import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

const QUOTES = ['Stay locked in.', 'September is coming.', 'Trust the data.', 'Focus.', 'Execute.']

export function QuoteHeader() {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setIndex((i) => (i + 1) % QUOTES.length), 8000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="quote-wrapper">
      <AnimatePresence mode="wait">
        <motion.h1
          key={index}
          className="quote-header"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.5 }}
        >
          {QUOTES[index]}
        </motion.h1>
      </AnimatePresence>
    </div>
  )
}
