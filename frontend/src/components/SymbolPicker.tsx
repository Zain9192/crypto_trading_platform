import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

interface Props { label: string; options: string[]; value: string; onChange: (value: string) => void }

/** Select-only combobox (WAI-ARIA APG pattern) whose open list shows ~3 options and scrolls. */
export default function SymbolPicker({ label, options, value, onChange }: Props) {
  const id = useId()
  const root = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(() => Math.max(0, options.indexOf(value)))

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  useEffect(() => {
    if (open) list.current?.children[active]?.scrollIntoView?.({ block: 'nearest' })
  }, [open, active])

  function show() { setActive(Math.max(0, options.indexOf(value))); setOpen(true) }
  function pick(index: number) { onChange(options[index]); setOpen(false) }
  function key(event: KeyboardEvent<HTMLDivElement>) {
    const last = options.length - 1
    const move = (index: number) => { event.preventDefault(); if (open) setActive(Math.min(last, Math.max(0, index))); else show() }
    switch (event.key) {
      case 'ArrowDown': return move(active + 1)
      case 'ArrowUp': return move(active - 1)
      case 'Home': return move(0)
      case 'End': return move(last)
      case 'Enter': case ' ': event.preventDefault(); return open ? pick(active) : show()
      case 'Escape': if (open) { event.preventDefault(); setOpen(false) } return
      case 'Tab': setOpen(false); return
      default: {
        if (event.key.length !== 1) return
        const letter = event.key.toUpperCase()
        const start = open ? active : options.indexOf(value)
        const order = [...options.keys()].map(i => (start + 1 + i) % options.length)
        const match = order.find(i => options[i].startsWith(letter))
        if (match === undefined) return
        if (open) setActive(match); else onChange(options[match])
      }
    }
  }

  return <div className="symbol-picker" ref={root}>
    <span id={`${id}-label`} className="symbol-picker-label">{label}</span>
    <div role="combobox" tabIndex={0} className="symbol-picker-button" aria-labelledby={`${id}-label`}
      aria-haspopup="listbox" aria-expanded={open} aria-controls={`${id}-list`}
      aria-activedescendant={open ? `${id}-opt-${active}` : undefined}
      onClick={() => (open ? setOpen(false) : show())} onKeyDown={key}>
      <span>{value}</span><span aria-hidden="true" className="symbol-picker-caret">{open ? '▴' : '▾'}</span>
    </div>
    {open && <ul role="listbox" id={`${id}-list`} ref={list} className="symbol-picker-list" aria-labelledby={`${id}-label`}>
      {options.map((option, index) => <li key={option} id={`${id}-opt-${index}`} role="option" aria-selected={option === value}
        className={index === active ? 'active' : undefined}
        onMouseDown={event => event.preventDefault()} onMouseEnter={() => setActive(index)} onClick={() => pick(index)}>
        {option}{option === value && <span aria-hidden="true">✓</span>}
      </li>)}
    </ul>}
  </div>
}
