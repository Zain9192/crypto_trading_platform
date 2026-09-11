import { createChart, ColorType, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts'
import { useEffect, useRef } from 'react'

import type { OhlcvCandle } from '../api/market'

interface CandlestickChartProps {
  candles: OhlcvCandle[]
}

export default function CandlestickChart({ candles }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeries = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeries = useRef<ISeriesApi<'Histogram'> | null>(null)
  const fitted = useRef(false)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const chart = createChart(container, {
      width: container.clientWidth,
      height: 390,
      layout: {
        background: { type: ColorType.Solid, color: '#0b1a30' },
        textColor: '#aebdd0',
      },
      grid: {
        vertLines: { color: '#172b46' },
        horzLines: { color: '#172b46' },
      },
      rightPriceScale: { borderColor: '#294362', scaleMargins: { top: 0.1, bottom: 0.25 } },
      timeScale: { borderColor: '#294362', timeVisible: true },
    })
    chartRef.current = chart
    candleSeries.current = chart.addCandlestickSeries({
      upColor: '#35c98d', downColor: '#f06868', borderVisible: false,
      wickUpColor: '#35c98d', wickDownColor: '#f06868',
    })
    volumeSeries.current = chart.addHistogramSeries({
      priceFormat: { type: 'volume' }, priceScaleId: 'volume',
    })
    volumeSeries.current.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
    const onResize = () => chart.applyOptions({ width: container.clientWidth })
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.remove()
      chartRef.current = null
      candleSeries.current = null
      volumeSeries.current = null
      fitted.current = false
    }
  }, [])

  useEffect(() => {
    const time = (candle: OhlcvCandle) => Math.floor(new Date(candle.timestamp).getTime() / 1000) as UTCTimestamp
    candleSeries.current?.setData(candles.map((candle) => ({
      time: time(candle), open: candle.open, high: candle.high, low: candle.low, close: candle.close,
    })))
    volumeSeries.current?.setData(candles.map((candle) => ({
      time: time(candle), value: candle.volume,
      color: candle.close >= candle.open ? '#35c98d80' : '#f0686880',
    })))
    // Preserve the user's zoom and pan when fresh data arrives.
    if (!fitted.current && candles.length) {
      chartRef.current?.timeScale().fitContent()
      fitted.current = true
    }
  }, [candles])

  return <div className="chart-canvas" ref={containerRef} aria-label="Candlestick price and volume chart" />
}
