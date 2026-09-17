import { useEffect, useRef, useState } from 'react'

export function useNotificationSocket(getToken: () => Promise<string>, onUpdate: () => void) {
  const tokenRef = useRef(getToken)
  const updateRef = useRef(onUpdate)
  tokenRef.current = getToken
  updateRef.current = onUpdate
  const [connected, setConnected] = useState(false)
  useEffect(() => {
    if (typeof WebSocket === 'undefined') return
    let stopped = false
    let socket: WebSocket | undefined
    let timer: number | undefined
    let previous = ''
    const retry = () => {
      setConnected(false)
      if (!stopped) timer = window.setTimeout(() => void connect(), 5000)
    }
    async function connect() {
      try {
        const token = await tokenRef.current()
        if (stopped) return
        const base = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
        const url = new URL(`${base.replace(/\/$/, '')}/notifications/ws`, window.location.origin)
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
        socket = new WebSocket(url)
        socket.onopen = () => socket?.send(token)
        socket.onmessage = event => {
          try {
            const data = JSON.parse(event.data)
            if (data.type !== 'notifications' || !Array.isArray(data.items)) return
            setConnected(true)
            // REST owns pagination and filtering; snapshots signal changes.
            if (event.data !== previous) { previous = event.data; updateRef.current() }
          } catch { /* Keep REST recovery available for malformed frames. */ }
        }
        socket.onclose = retry
        socket.onerror = () => socket?.close()
      } catch { if (!stopped) retry() }
    }
    void connect()
    return () => {
      stopped = true
      window.clearTimeout(timer)
      if (socket) { socket.onclose = null; socket.close() }
    }
  }, [])
  return connected
}
