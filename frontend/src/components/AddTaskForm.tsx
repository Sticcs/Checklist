import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CATEGORIES, CAT_KEYS, PRIORITIES, PRI_KEYS } from '../constants'
import { computeDueDate, DUE_PRESET_ORDER, type DuePreset } from '../utils/dueDatePresets'
import { isTypingElement } from '../utils/isTypingElement'
import { useAddTask } from '../hooks/useTasks'

const DUE_KEYS: Record<DuePreset, string> = {
  Today: '1',
  Tomorrow: '2',
  'This week': '3',
  'Next week': '4',
  Custom: '5',
  'No date': '6',
}

interface Props {
  onAdded?: (taskId: number) => void
  hasTasks?: boolean
}

export function AddTaskForm({ onAdded, hasTasks }: Props) {
  const [text, setText] = useState('')
  const [textLocked, setTextLocked] = useState(false)
  const [category, setCategory] = useState<string | null>(null)
  const [customCategory, setCustomCategory] = useState('')
  const [priority, setPriority] = useState<string | null>(null)
  const [duePreset, setDuePreset] = useState<DuePreset | null>(null)
  const [customDueDate, setCustomDueDate] = useState('')

  const addTask = useAddTask()
  const customCategoryRef = useRef<HTMLInputElement>(null)

  const categoryVisible = textLocked
  const priorityVisible = textLocked && category !== null
  const dueVisible = textLocked && category !== null && priority !== null
  const dueReady = duePreset !== null && (duePreset !== 'Custom' || customDueDate !== '')
  const addVisible = textLocked && category !== null && priority !== null && dueReady

  useEffect(() => {
    if (category === 'Custom') customCategoryRef.current?.focus()
  }, [category])

  // Typing anywhere on the page (when nothing is already being typed into,
  // and the progressive-disclosure flow hasn't started yet) redirects focus
  // to the main task input so the keystroke lands there - no explicit click
  // needed. '/' and '`' are reserved for the subtask-focus and scratchpad
  // hotkeys respectively, so they're excluded here.
  useEffect(() => {
    if (textLocked) return

    const handler = (e: KeyboardEvent) => {
      if (isTypingElement(document.activeElement)) return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key.length !== 1) return
      if (e.key === '/' || e.key === '`') return

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
  }

  const submit = () => {
    if (!addVisible || !category || !priority || !duePreset) return
    const finalCategory = category === 'Custom' ? customCategory.trim() || 'General' : category
    const dueDate = computeDueDate(duePreset, customDueDate || null)
    addTask.mutate(
      { text: text.trim(), priority, category: finalCategory, dueDate },
      {
        onSuccess: (task) => {
          onAdded?.(task.id)
          resetAll()
        },
      }
    )
  }

  const handleTextChange = (value: string) => {
    setText(value)
    if (value.trim() === '') {
      setTextLocked(false)
      setCategory(null)
      setPriority(null)
      setDuePreset(null)
    }
  }

  const handleTextKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter' || text.trim() === '') return
    e.preventDefault()
    if (!textLocked) {
      setTextLocked(true)
      e.currentTarget.blur()
    } else if (addVisible) {
      submit()
    }
  }

  // Hotkeys only engage once the text is locked (the progressive disclosure
  // flow has actually started) and focus isn't inside a text input - so
  // there's no "first keystroke eaten by a hotkey" clash to work around the
  // way the Streamlit version needed: before locking, keystrokes just go to
  // the plain text input like any normal page.
  useEffect(() => {
    if (!textLocked) return

    const handler = (e: KeyboardEvent) => {
      if (isTypingElement(document.activeElement)) return

      const key = e.key.toLowerCase()
      for (const [cat, hotkey] of Object.entries(CAT_KEYS)) {
        if (hotkey && hotkey.toLowerCase() === key) {
          e.preventDefault()
          setCategory(cat)
          return
        }
      }
      for (const [pri, hotkey] of Object.entries(PRI_KEYS)) {
        if (hotkey.toLowerCase() === key) {
          e.preventDefault()
          setPriority(pri)
          return
        }
      }
      for (const [preset, hotkey] of Object.entries(DUE_KEYS)) {
        if (hotkey === key) {
          e.preventDefault()
          setDuePreset(preset as DuePreset)
          return
        }
      }
      if (e.key === 'Enter' && addVisible) {
        e.preventDefault()
        submit()
      }
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textLocked, addVisible, category, priority, duePreset, customDueDate, text])

  // A single running hint under the input: onboarding copy while it's empty,
  // then one instruction per progressive-disclosure step as the flow
  // advances - so there's always exactly one thing telling the user what to
  // do next.
  const hint = (() => {
    if (text.trim() === '' && !textLocked) {
      // Only makes sense before there's anything in the list yet - once a
      // task exists it isn't the user's "first" task anymore, and an empty
      // box doesn't need a prompt at all.
      if (hasTasks) return null
      return { text: 'Start typing to enter your first task.', tone: 'onboarding' }
    }
    if (!textLocked) return { text: 'Press Enter to lock in your text.', tone: 'step' }
    if (category === null) return { text: 'Select a category.', tone: 'step' }
    if (priority === null) return { text: 'Select a priority.', tone: 'step' }
    if (!dueReady) return { text: 'Select a due date.', tone: 'step' }
    return { text: 'Click "Add task" to finish.', tone: 'step' }
  })()

  const sectionMotion = {
    initial: { opacity: 0, height: 0 },
    animate: { opacity: 1, height: 'auto' },
    exit: { opacity: 0, height: 0 },
    transition: { duration: 0.25, ease: 'easeOut' as const },
  }

  return (
    <div className="add-task-form">
      <input
        className="task-text-input"
        placeholder="E.g., Review Big O time complexity"
        value={text}
        onChange={(e) => handleTextChange(e.target.value)}
        onKeyDown={handleTextKeyDown}
      />
      {hint && <p className={`entry-hint entry-hint-${hint.tone}`}>{hint.text}</p>}

      <AnimatePresence>
        {categoryVisible && (
          <motion.div key="category-row" className="option-row" {...sectionMotion}>
            <p className="option-row-label">Category</p>
            <div className="option-row-buttons">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  className={category === cat ? 'btn-option btn-primary' : 'btn-option'}
                  aria-pressed={category === cat}
                  onClick={() => setCategory(cat)}
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
                  // Hands off to the priority row's click/hotkey flow, same
                  // as the main text input blurring itself once locked.
                  e.currentTarget.blur()
                }}
              />
            )}
          </motion.div>
        )}

        {priorityVisible && (
          <motion.div key="priority-row" className="option-row" {...sectionMotion}>
            <p className="option-row-label">Priority</p>
            <div className="option-row-buttons">
              {PRIORITIES.map((pri) => (
                <button
                  key={pri}
                  type="button"
                  className={priority === pri ? 'btn-option btn-primary' : 'btn-option'}
                  aria-pressed={priority === pri}
                  onClick={() => setPriority(pri)}
                >
                  {pri} [{PRI_KEYS[pri]}]
                </button>
              ))}
            </div>
          </motion.div>
        )}

        {dueVisible && (
          <motion.div key="due-row" className="option-row" {...sectionMotion}>
            <p className="option-row-label">Due</p>
            <div className="option-row-buttons">
              {DUE_PRESET_ORDER.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  className={duePreset === preset ? 'btn-option btn-primary' : 'btn-option'}
                  aria-pressed={duePreset === preset}
                  onClick={() => setDuePreset(preset)}
                >
                  {preset} [{DUE_KEYS[preset]}]
                </button>
              ))}
            </div>
            {duePreset === 'Custom' && (
              <input
                type="date"
                className="custom-input"
                value={customDueDate}
                onChange={(e) => setCustomDueDate(e.target.value)}
              />
            )}
          </motion.div>
        )}

        {addVisible && (
          <motion.button
            key="add-task-btn"
            type="button"
            className="btn-add-task btn-primary"
            onClick={submit}
            {...sectionMotion}
          >
            Add task
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  )
}
