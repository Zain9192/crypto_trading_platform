import { createChart, ColorType, type IChartApi, type UTCTimestamp } from 'lightweight-charts'
import { useEffect, useRef } from 'react'

import type { OhlcvCandle } from '../api/market'

interface CandlestickChartProps {
  candles: OhlcvCandle[]
}

export default function CandlestickChart({ candles }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

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
      rightPriceScale: { borderColor: '#294362' },
      timeScale: { borderColor: '#294362', timeVisible: true },
    })
    chartRef.current = chart
    const series = chart.addCandlestickSeries({
      upColor: '#35c98d',
      downColor: '#f06868',
      borderVisible: false,
      wickUpColor: '#35c98d',
      wickDownColor: '#f06868',
    })
    series.setData(
      candles.map((candle) => ({
        time: Math.floor(new Date(candle.timestamp).getTime() / 1000) as UTCTimestamp,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      })),
    )
    chart.timeScale().fitContent()

    const onResize = () => chart.applyOptions({ width: container.clientWidth })
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.remove()
      chartRef.current = null
    }
  }, [candles])

  return <div className="chart-canvas" ref={containerRef} aria-label="Candlestick price chart" />
}
