import '@testing-library/jest-dom/vitest'
import { useState } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import SymbolPicker from './SymbolPicker'

const OPTIONS = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL']
function Harness({ onChange }: { onChange: (v: string) => void }) {
  const [value, setValue] = useState('BTC')
  return <><SymbolPicker label="Symbol" options={OPTIONS} value={value} onChange={v => { setValue(v); onChange(v) }} /><button>outside</button></>
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('opens on click, marks the selection and picks with the mouse', () => {
  const onChange = vi.fn()
  render(<Harness onChange={onChange} />)
  const box = screen.getByRole('combobox', { name: 'Symbol' })
  expect(box).toHaveAttribute('aria-expanded', 'false')
  fireEvent.click(box)
  expect(box).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('option', { name: /BTC/ })).toHaveAttribute('aria-selected', 'true')
  fireEvent.click(screen.getByRole('option', { name: 'SOL' }))
  expect(onChange).toHaveBeenCalledWith('SOL')
  expect(box).toHaveTextContent('SOL')
  expect(screen.queryByRole('listbox')).toBeNull()
})

it('supports arrow keys, Enter, Home/End, Escape and letter jump', () => {
  const onChange = vi.fn()
  render(<Harness onChange={onChange} />)
  const box = screen.getByRole('combobox', { name: 'Symbol' })
  fireEvent.keyDown(box, { key: 'ArrowDown' })
  expect(screen.getByRole('listbox')).toBeInTheDocument()
  fireEvent.keyDown(box, { key: 'ArrowDown' })
  fireEvent.keyDown(box, { key: 'ArrowDown' })
  expect(box.getAttribute('aria-activedescendant')).toMatch(/opt-2$/)
  fireEvent.keyDown(box, { key: 'Enter' })
  expect(onChange).toHaveBeenLastCalledWith('BNB')
  fireEvent.keyDown(box, { key: 'Enter' })
  fireEvent.keyDown(box, { key: 'End' })
  fireEvent.keyDown(box, { key: ' ' })
  expect(onChange).toHaveBeenLastCalledWith('SOL')
  fireEvent.keyDown(box, { key: 'Enter' })
  fireEvent.keyDown(box, { key: 'Home' })
  fireEvent.keyDown(box, { key: 'Escape' })
  expect(screen.queryByRole('listbox')).toBeNull()
  expect(box).toHaveTextContent('SOL')
  fireEvent.keyDown(box, { key: 'x' })
  expect(onChange).toHaveBeenLastCalledWith('XRP')
})

it('closes when clicking outside', () => {
  render(<Harness onChange={vi.fn()} />)
  fireEvent.click(screen.getByRole('combobox', { name: 'Symbol' }))
  expect(screen.getByRole('listbox')).toBeInTheDocument()
  fireEvent.mouseDown(screen.getByRole('button', { name: 'outside' }))
  expect(screen.queryByRole('listbox')).toBeNull()
})
