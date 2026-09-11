import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import CandlestickChart from './CandlestickChart'
import type { OhlcvCandle } from '../api/market'

const mocks = vi.hoisted(() => {
  const candleData = vi.fn(), volumeData = vi.fn(), fitContent = vi.fn(), remove = vi.fn()
  const createChart = vi.fn(() => ({
    addCandlestickSeries: () => ({ setData: candleData }),
    addHistogramSeries: () => ({ setData: volumeData, priceScale: () => ({ applyOptions: vi.fn() }) }),
    timeScale: () => ({ fitContent }), applyOptions: vi.fn(), remove,
  }))
  return { candleData, volumeData, fitContent, remove, createChart }
})
vi.mock('lightweight-charts', () => ({ createChart: mocks.createChart, ColorType: { Solid: 'solid' } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
it('updates price and volume without resetting chart zoom on refresh', () => {
  const candle: OhlcvCandle = {
    symbol: 'BTC', interval: '1d', timestamp: '2026-01-01T00:00:00Z',
    open: 10, high: 12, low: 9, close: 11, volume: 100, quote_asset: 'USDT', provider: 'binance',
  }
  const { rerender, unmount } = render(<CandlestickChart candles={[candle]} />)
  rerender(<CandlestickChart candles={[{ ...candle, close: 12, volume: 120 }]} />)
  expect(mocks.createChart).toHaveBeenCalledTimes(1)
  expect(mocks.fitContent).toHaveBeenCalledTimes(1)
  expect(mocks.candleData.mock.lastCall?.[0][0].close).toBe(12)
  expect(mocks.volumeData.mock.lastCall?.[0][0].value).toBe(120)
  unmount()
  expect(mocks.remove).toHaveBeenCalledTimes(1)
})
