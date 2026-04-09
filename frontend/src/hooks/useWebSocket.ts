'use client'

import { useEffect, useRef, useState, useCallback } from 'react'

export interface WebSocketMessage {
  type: string
  [key: string]: unknown
}

interface UseWebSocketOptions {
  url: string
  protocols?: string | string[]
  onOpen?: (event: Event) => void
  onMessage?: (message: WebSocketMessage) => void
  onError?: (event: Event) => void
  onClose?: (event: CloseEvent) => void
  shouldReconnect?: boolean
  reconnectInterval?: number
  maxReconnectAttempts?: number
  enabled?: boolean // 接続を有効にするかどうか
}

interface WebSocketState {
  readyState: number
  lastMessage: WebSocketMessage | null
  connectionStatus: 'Connecting' | 'Open' | 'Closing' | 'Closed'
}

export function useWebSocket({
  url,
  protocols,
  onOpen,
  onMessage,
  onError,
  onClose,
  shouldReconnect = true,
  reconnectInterval = 5000,
  maxReconnectAttempts = 3,
  enabled = true,
}: UseWebSocketOptions) {
  const [state, setState] = useState<WebSocketState>({
    readyState: WebSocket.CONNECTING,
    lastMessage: null,
    connectionStatus: 'Connecting',
  })

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined)
  const reconnectAttemptsRef = useRef(0)
  const urlRef = useRef(url)

  // URL変更の追跡
  useEffect(() => {
    urlRef.current = url
  }, [url])

  const getConnectionStatus = useCallback((readyState: number): WebSocketState['connectionStatus'] => {
    switch (readyState) {
      case WebSocket.CONNECTING:
        return 'Connecting'
      case WebSocket.OPEN:
        return 'Open'
      case WebSocket.CLOSING:
        return 'Closing'
      case WebSocket.CLOSED:
        return 'Closed'
      default:
        return 'Closed'
    }
  }, [])

  const connect = useCallback(() => {
    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        return
      }

      wsRef.current = new WebSocket(urlRef.current, protocols)

      wsRef.current.onopen = (event) => {
        // 接続確立後にトークンを送信（URLパラメータに含めない）
        const token = localStorage.getItem('access_token')
        if (token && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'auth', token }))
        }
        setState((prev) => ({
          ...prev,
          readyState: WebSocket.OPEN,
          connectionStatus: 'Open',
        }))
        reconnectAttemptsRef.current = 0
        onOpen?.(event)
      }

      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WebSocketMessage
          setState((prev) => ({
            ...prev,
            lastMessage: message,
          }))
          onMessage?.(message)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      wsRef.current.onerror = (event) => {
        console.error('WebSocket error occurred:', event)
        console.error('WebSocket URL:', wsUrl)
        console.error('ReadyState:', wsRef.current?.readyState)
        onError?.(event)
      }

      wsRef.current.onclose = (event) => {
        setState((prev) => ({
          ...prev,
          readyState: WebSocket.CLOSED,
          connectionStatus: 'Closed',
        }))

        onClose?.(event)

        // 自動再接続（異常終了の場合のみ）
        if (shouldReconnect &&
            reconnectAttemptsRef.current < maxReconnectAttempts &&
            (event.code !== 1000 && event.code !== 1001)) { // 正常終了以外の場合
          reconnectAttemptsRef.current += 1

          // 指数バックオフ: 最初は5秒、その後10秒、15秒
          const backoffDelay = reconnectInterval * reconnectAttemptsRef.current

          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, backoffDelay)
        }
      }
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error)
    }
  }, [url, protocols, onOpen, onMessage, onError, onClose, shouldReconnect, reconnectInterval, maxReconnectAttempts, enabled])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }

    if (wsRef.current) {
      wsRef.current.close()
    }
  }, [])

  const sendMessage = useCallback((message: WebSocketMessage | string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const messageString = typeof message === 'string' ? message : JSON.stringify(message)
      wsRef.current.send(messageString)
      return true
    }
    return false
  }, [])

  // 特定のチャンネルに購読
  const subscribe = useCallback((channel: string) => {
    return sendMessage({
      type: 'subscribe',
      channel: channel,
    })
  }, [sendMessage])

  // 特定のチャンネルから購読解除
  const unsubscribe = useCallback((channel: string) => {
    return sendMessage({
      type: 'unsubscribe',
      channel: channel,
    })
  }, [sendMessage])

  // ヘルスチェック
  const ping = useCallback(() => {
    return sendMessage({
      type: 'ping',
    })
  }, [sendMessage])

  // 定期的なpingを送信（接続がオープンの時のみ）
  useEffect(() => {
    if (!enabled) return // enabledがfalseの場合はpingを送信しない

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        // ping関数を直接呼ばずに、sendMessage直接呼び出し
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'ping' }))
        }
      }
    }, 45000) // 45秒ごとに変更して負荷を軽減

    return () => {
      clearInterval(pingInterval)
    }
  }, [enabled]) // pingを依存関係から削除

  // 接続開始（enabledがtrueの時のみ）
  useEffect(() => {
    if (enabled) {
      connect()
    } else {
      // 直接切断処理を実行
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }

      // 状態もリセット
      setState({
        readyState: WebSocket.CLOSED,
        lastMessage: null,
        connectionStatus: 'Closed',
      })
    }

    return () => {
      // クリーンアップ時は直接切断
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [enabled]) // connectとdisconnectを依存関係から削除

  // ページ離脱時の処理
  useEffect(() => {
    const handleBeforeUnload = () => {
      disconnect()
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [disconnect])

  return {
    ...state,
    sendMessage,
    subscribe,
    unsubscribe,
    ping,
    connect,
    disconnect,
  }
}