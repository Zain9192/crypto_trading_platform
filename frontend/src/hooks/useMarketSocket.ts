import { useEffect } from 'react'

import type { MarketAsset } from '../api/market'

interface MarketSnapshotMessage {
  type: 'market_snapshot'
  generated_at: string
  refresh_seconds: number
  items: MarketAsset[]
}

function marketSocketUrl(): string {
  const explicit = import.meta.env.VITE_MARKET_WS_URL
  if (explicit) return explicit
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/v1/market/ws/prices?limit=50`
}

export function useMarketSocket(onSnapshot: (items: MarketAsset[]) => void): void {
  useEffect(() => {
    if (typeof WebSocket === 'undefined') return

    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let closedByEffect = false

    const connect = () => {
      socket = new WebSocket(marketSocketUrl())
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as MarketSnapshotMessage
          if (message.type === 'market_snapshot' && Array.isArray(message.items)) {
            onSnapshot(message.items)
          }
        } catch {
          // Ignore malformed frames and keep the stream alive.
        }
      }
      socket.onclose = () => {
        if (!closedByEffect) {
          reconnectTimer = window.setTimeout(connect, 3000)
        }
      }
    }

    connect()
    return () => {
      closedByEffect = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [onSnapshot])
}
