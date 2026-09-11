import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { CATEGORIES, CAT_KEYS, PRIORITIES, PRI_KEYS, SHOPPING_CATEGORY } from '../constants'
import { computeDueDate, DUE_PRESET_ORDER, type DuePreset } from '../utils/dueDatePresets'
import { isTypingElement } from '../utils/isTypingElement'
import { useAddTask } from '../hooks/useTasks'
import { useDraftText } from '../hooks/useDraftText'
import { DateInput } from './DateInput'

const DUE_KEYS: Record<DuePreset, string> = {
  Today: '1',
  Tomorrow: '2',
  'This week': '3',
  'Next week': '4',
  Custom: '5',
  'No date': '6',
}

// How long a picked button stays visibly green before its row swaps to the
// next step - see selectWithFlash below.
const FLASH_MS = 320

type Step = 'category' | 'priority' | 'due' | 'confirm'

// Rendered via a portal straight into <body> (same pattern as
// ExpandOverlay.tsx) - .task-entry-panel, this overlay's DOM ancestor if it
// weren't portaled, has its own backdrop-filter (glass-panel styling),
// which - like transform/filter - establishes a new containing block for
// position:fixed descendants. Without the portal, this vignette's "inset: 0"
// resolved against .task-entry-panel's own small box instead of the actual
// viewport, confining the whole category/priority/due/confirm flow to a
// tiny area overlapping whatever sat below it (most visibly the sidebar on
// the mobile layout, where the two panels' content rendered tangled
// together).
//
// Must be a genuine component (not createPortal() called inline as
// AnimatePresence's own child expression) - AnimatePresence needs a real,
// cloneable element as its direct child to track for exit animations; hand
// it a raw ReactPortal directly and it silently fails to render anything.
function TaskEntryVignetteOverlay({ onCancel, children }: { onCancel: () => void; children: React.ReactNode }) {
  return createPortal(
    <motion.div
      className="task-entry-vignette"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="task-entry-vignette-panel">{children}</div>
    </motion.div>,
    document.body
  )
}

interface Props {
  onAdded?: (taskId: number) => void
  hasTasks?: boolean
}

export function AddTaskForm({ onAdded, hasTasks }: Props) {
  // Mirrored to localStorage (see useDraftText) so text you're mid-typing
  // survives an accidental reload or a dropped connection instead of just
  // vanishing - restored automatically the next time this form mounts.
  const [text, setText] = useDraftText('quick-add')
  const [textLocked, setTextLocked] = useState(false)
  const [category, setCategory] = useState<string | null>(null)
  const [customCategory, setCustomCategory] = useState('')
  const [priority, setPriority] = useState<string | null>(null)
  const [duePreset, setDuePreset] = useState<DuePreset | null>(null)
  const [customDueDate, setCustomDueDate] = useState('')

  // Which button row the overlay is currently showing - deliberately a
  // separate piece of state from category/priority/duePreset above (rather
  // than deriving "which row is visible" from whichever of those is still
  // null, the way this form used to work), so a just-picked value can
  // finish its green flash (see flashValue) while the row underneath it
  // hasn't swapped to the next step yet.
  const [step, setStep] = useState<Step>('category')
  const [flashValue, setFlashValue] = useState<string | null>(null)

  const addTask = useAddTask()
  const customCategoryRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (category === 'Custom') customCategoryRef.current?.focus()
  }, [category])

  // Typing anywhere on the page (when nothing is already being typed into,
  // and the progressive-disclosure flow hasn't started yet) redirects focus
  // to the main task input so the keystroke lands there - no explicit click
  // needed. '/', '`', and '?' are reserved for the subtask-focus, scratchpad,
  // and keyboard-shortcuts-help hotkeys respectively, so they're excluded
  // here - otherwise this handler (which mounts before that help hotkey's
  // own listener) moves focus into the task input first, and by the time
  // the other handler checks whether focus is in a text field, it already
  // is, so it thinks the user was "typing" and never fires.
  useEffect(() => {
    if (textLocked) return

    const handler = (e: KeyboardEvent) => {
      if (isTypingElement(document.activeElement)) return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key.length !== 1) return
      if (e.key === '/' || e.key === '`' || e.key === '?') return

      const input = document.querySelector('.task-text-input') as HTMLInputElement | null
      input?.focus()
      // No preventDefault: focus lands before this same keydown's default
      // character-insertion behavior runs, so the keystroke types into the
      // input we just focused instead of being lost.
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [textLocked])

  const resetAll = () => {
    setText('')
    setTextLocked(false)
    setCategory(null)
    setCustomCategory('')
    setPriority(null)
    setDuePreset(null)
    setCustomDueDate('')
    setStep('category')
    setFlashValue(null)
  }

  const lockText = () => {
    if (text.trim() === '') return
    setTextLocked(true)
    setStep('category')
    ;(document.activeElement as HTMLElement | null)?.blur()
  }

  // Accepts an optional freshly-typed custom date so Enter-to-submit inside
  // the date field itself (see DateInput's onEnter below) can go straight
  // through with the value just read off the DOM, without waiting on
  // customDueDate state to catch up first.
  const submit = (customDateOverride?: string) => {
    if (!category || !priority || !duePreset) return
    const effectiveCustomDate = customDateOverride ?? customDueDate
    if (duePreset === 'Custom' && effectiveCustomDate === '') return
    const finalCategory = category === 'Custom' ? customCategory.trim() || 'General' : category
    const dueDate = computeDueDate(duePreset, effectiveCustomDate || null)
    // Collapse the overlay immediately - the mutation is optimistic, so the
    // task itself already appears in the list right away too. Waiting for
    // the server round trip here just left the buttons sitting on screen
    // for however long the request took, with nothing left to do.
    resetAll()
    addTask.mutate(
      { text: text.trim(), priority, category: finalCategory, dueDate },
      {
        onSuccess: (task) => onAdded?.(task.id),
      }
    )
  }

  // The one place a picked value actually commits - holds the row on screen
  // (with `value` shown green) for FLASH_MS before advancing `step` and
  // clearing the flash, so the "briefly goes green, then the whole row
  // transitions to the next set" beat is visible instead of an instant swap.
  const selectWithFlash = (value: string, commit: () => void) => {
    setFlashValue(value)
    window.setTimeout(() => {
      commit()
      setFlashValue(null)
    }, FLASH_MS)
  }

  const pickCategory = (cat: string) => {
    if (cat === 'Custom') {
      setCategory('Custom')
      return
    }
    selectWithFlash(cat, () => {
      setCategory(cat)
      if (cat === SHOPPING_CATEGORY) {
        // Shopping skips straight to confirm - no priority/due to ask for.
        setPriority('Medium')
        setDuePreset('No date')
        setStep('confirm')
      } else {
        setStep('priority')
      }
    })
  }

  const commitCustomCategory = () => {
    if (customCategory.trim() === '') return
    selectWithFlash('Custom', () => setStep('priority'))
  }

  const pickPriority = (pri: string) => {
    selectWithFlash(pri, () => {
      setPriority(pri)
      setStep('due')
    })
  }

  const pickDue = (preset: DuePreset) => {
    if (preset === 'Custom') {
      setDuePreset('Custom')
      return
    }
    selectWithFlash(preset, () => {
      setDuePreset(preset)
      setStep('confirm')
    })
  }

  const commitCustomDue = (dateStr: string) => {
    if (dateStr === '') return
    setCustomDueDate(dateStr)
    selectWithFlash('Custom', () => setStep('confirm'))
  }

  const handleTextChange = (value: string) => {
    setText(value)
    if (value.trim() === '') resetAll()
  }

  const handleTextKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter' || text.trim() === '') return
    e.preventDefault()
    if (!textLocked) lockText()
  }

  const cancelOverlay = () => {
    setText('')
    resetAll()
  }

  // Hotkeys only engage once the overlay is open, mapped to whichever step
  // is currently visible (matches the button row actually on screen) - and
  // focus isn't inside a text input, so there's no "first keystroke eaten
  // by a hotkey" clash to work around the way the Streamlit version needed.
  useEffect(() => {
    if (!textLocked) return

    const handler = (e: KeyboardEvent) => {
      if (isTypingElement(document.activeElement)) return

      if (e.key === 'Escape') {
        e.preventDefault()
        cancelOverlay()
        return
      }

      const key = e.key.toLowerCase()
      if (step === 'category') {
        for (const [cat, hotkey] of Object.entries(CAT_KEYS)) {
          if (hotkey && hotkey.toLowerCase() === key) {
            e.preventDefault()
            pickCategory(cat)
            return
          }
        }
      } else if (step === 'priority') {
        for (const [pri, hotkey] of Object.entries(PRI_KEYS)) {
          if (hotkey.toLowerCase() === key) {
            e.preventDefault()
            pickPriority(pri)
            return
          }
        }
      } else if (step === 'due') {
        for (const [preset, hotkey] of Object.entries(DUE_KEYS)) {
          if (hotkey === key) {
            e.preventDefault()
            pickDue(preset as DuePreset)
            return
          }
        }
      } else if (step === 'confirm' && e.key === 'Enter') {
        e.preventDefault()
        submit()
      }
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textLocked, step, category, priority, duePreset, customDueDate, customCategory, text])

  const hint = (() => {
    if (text.trim() === '' && !textLocked) {
      // Only makes sense before there's anything in the list yet - once a
      // task exists it isn't the user's "first" task anymore, and an empty
      // box doesn't need a prompt at all.
      if (hasTasks) return null
      return 'Start typing to enter your first task.'
    }
    if (!textLocked) return 'Press Enter (or the green button) to continue.'
    return null
  })()

  const sectionMotion = {
    initial: { opacity: 0, y: 16 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: 16 },
    transition: { duration: 0.2, ease: 'easeOut' as const },
  }

  const categoryGlowClass = (cat: string): string => {
    if (cat === 'Assessment') return 'btn-option btn-option-glow-red'
    if (cat === SHOPPING_CATEGORY) return 'btn-option btn-option-glow-blue'
    return 'btn-option'
  }

  const optionClass = (stepName: Step, value: string, selected: boolean, baseClass: string): string => {
    if (step === stepName && flashValue === value) return `${baseClass} flashing-green`
    return selected ? `${baseClass} btn-primary` : baseClass
  }

  return (
    <div className="add-task-form">
      <div className="task-entry-row">
        <input
          className="task-text-input"
          placeholder="E.g., Review Big O time complexity"
          value={text}
          onChange={(e) => handleTextChange(e.target.value)}
          onKeyDown={handleTextKeyDown}
          disabled={textLocked}
        />
        {/* The physical-Enter-key equivalent, as an actual button - mainly
            for touch/mobile, where there's no keyboard "Enter" to press
            without bringing up the on-screen one. */}
        <button
          type="button"
          className="task-entry-enter-btn"
          title="Enter"
          disabled={text.trim() === '' || textLocked}
          onClick={lockText}
        >
          ➤
        </button>
      </div>
      {hint && <p className="entry-hint entry-hint-step">{hint}</p>}

      {/* A dark vignette anchored to the bottom of the screen, not an
          inline row under the input - only shows once the text is locked
          in, and holds every remaining step (category -> priority -> due ->
          confirm) so the whole rest of the add-a-task flow happens as one
          focused, dynamic interaction instead of a stack of boxes pushing
          the page down. See TaskEntryVignetteOverlay above for why this is
          portaled into <body>. */}
      <AnimatePresence>
        {textLocked && (
          <TaskEntryVignetteOverlay onCancel={cancelOverlay}>
              <AnimatePresence mode="wait">
                {step === 'category' && (
                  <motion.div key="category-row" className="option-row" {...sectionMotion}>
                    <p className="option-row-label">Category</p>
                    <div className="option-row-buttons">
                      {CATEGORIES.map((cat) => (
                        <button
                          key={cat}
                          type="button"
                          className={optionClass('category', cat, category === cat, categoryGlowClass(cat))}
                          aria-pressed={category === cat}
                          onClick={() => pickCategory(cat)}
                        >
                          {CAT_KEYS[cat] ? `${cat} [${CAT_KEYS[cat]}]` : cat}
                        </button>
                      ))}
                    </div>
                    {category === 'Custom' && (
                      <input
                        ref={customCategoryRef}
                        className="custom-input"
                        placeholder="E.g., Groceries"
                        value={customCategory}
                        onChange={(e) => setCustomCategory(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key !== 'Enter') return
                          e.preventDefault()
                          commitCustomCategory()
                        }}
                      />
                    )}
                  </motion.div>
                )}

                {step === 'priority' && (
                  <motion.div key="priority-row" className="option-row" {...sectionMotion}>
                    <p className="option-row-label">Priority</p>
                    <div className="option-row-buttons">
                      {PRIORITIES.map((pri) => (
                        <button
                          key={pri}
                          type="button"
                          className={optionClass('priority', pri, priority === pri, 'btn-option')}
                          aria-pressed={priority === pri}
                          onClick={() => pickPriority(pri)}
                        >
                          {pri} [{PRI_KEYS[pri]}]
                        </button>
                      ))}
                    </div>
                  </motion.div>
                )}

                {step === 'due' && (
                  <motion.div key="due-row" className="option-row" {...sectionMotion}>
                    <p className="option-row-label">Due</p>
                    <div className="option-row-buttons">
                      {DUE_PRESET_ORDER.map((preset) => (
                        <button
                          key={preset}
                          type="button"
                          className={optionClass('due', preset, duePreset === preset, 'btn-option')}
                          aria-pressed={duePreset === preset}
                          onClick={() => pickDue(preset)}
                        >
                          {preset} [{DUE_KEYS[preset]}]
                        </button>
                      ))}
                    </div>
                    {duePreset === 'Custom' && (
                      <DateInput
                        className="custom-input"
                        value={customDueDate}
                        autoFocus
                        onCommit={() => {}}
                        onEnter={commitCustomDue}
                      />
                    )}
                  </motion.div>
                )}

                {step === 'confirm' && (
                  <motion.div key="confirm-row" className="task-entry-confirm-row" {...sectionMotion}>
                    <p className="option-row-label">Ready to add “{text.trim()}”</p>
                    <button type="button" className="task-entry-confirm-btn" onClick={() => submit()}>
                      ✓ Enter
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
          </TaskEntryVignetteOverlay>
        )}
      </AnimatePresence>
    </div>
  )
}
