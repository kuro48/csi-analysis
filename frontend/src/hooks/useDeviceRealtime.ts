'use client'

import { useEffect, useCallback } from 'react'
import { useWebSocket, WebSocketMessage } from './useWebSocket'

interface Device {
  id: string
  device_id: string
  device_name: string
  device_type: string
  location?: string
  status: string
  connection_status: string
  last_seen?: string
  created_at: string
  is_active: boolean
}

interface UseDeviceRealtimeProps {
  onDeviceStatusUpdate?: (device: Device) => void
  onDeviceCreated?: (device: Device) => void
  onDeviceUpdated?: (device: Device) => void
  onDeviceDeleted?: (deviceId: string) => void
  onDeviceStatistics?: (statistics: Record<string, unknown>) => void
  onHeartbeat?: (deviceId: string, data: Record<string, unknown>) => void
}

export function useDeviceRealtime({
  onDeviceStatusUpdate,
  onDeviceCreated,
  onDeviceUpdated,
  onDeviceDeleted,
  onDeviceStatistics,
  onHeartbeat
}: UseDeviceRealtimeProps) {
  // メッセージハンドラー
  const handleMessage = useCallback((message: WebSocketMessage) => {
    const { type, data, device_id } = message

    switch (type) {
      case 'device_status':
        onDeviceStatusUpdate?.(data as Device)
        break
      case 'device_created':
        onDeviceCreated?.(data as Device)
        break
      case 'device_updated':
        onDeviceUpdated?.(data as Device)
        break
      case 'device_deleted':
        onDeviceDeleted?.(device_id as string)
        break
      case 'device_statistics':
        onDeviceStatistics?.(data as Record<string, unknown>)
        break
      case 'device_heartbeat':
        onHeartbeat?.(device_id as string, data as Record<string, unknown>)
        break
      case 'connection_established':
      case 'subscribed':
      case 'unsubscribed':
      case 'pong':
        // これらはシステムメッセージなので処理不要
        break
      default:
        // Unknown message type
    }
  }, [
    onDeviceStatusUpdate,
    onDeviceCreated,
    onDeviceUpdated,
    onDeviceDeleted,
    onDeviceStatistics,
    onHeartbeat
  ])

  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/api/v2/ws/realtime'

  const {
    connectionStatus,
    subscribe,
    unsubscribe,
    sendMessage
  } = useWebSocket({
    url: wsUrl,
    enabled: true,
    shouldReconnect: true,
    onMessage: handleMessage,
    onOpen: () => {
      // WebSocket connected
    },
    onClose: () => {
      // WebSocket disconnected
    },
    onError: (error) => {
      console.error('Device realtime WebSocket error:', error)
    },
  })

  const isConnected = connectionStatus === 'Open'

  // デバイス状態チャンネルに購読
  useEffect(() => {
    if (isConnected) {
      subscribe('device_status')

      return () => {
        unsubscribe('device_status')
      }
    }
  }, [isConnected, subscribe, unsubscribe, handleMessage])

  // 特定のデバイスを監視する関数
  const subscribeToDevice = useCallback((deviceId: string) => {
    if (isConnected) {
      subscribe(`device_${deviceId}`)
    }
  }, [isConnected, subscribe, handleMessage])

  // 特定のデバイスの監視を停止する関数
  const unsubscribeFromDevice = useCallback((deviceId: string) => {
    if (isConnected) {
      unsubscribe(`device_${deviceId}`)
    }
  }, [isConnected, unsubscribe])

  // 統計情報の更新を要求
  const requestStatisticsUpdate = useCallback(() => {
    if (isConnected) {
      sendMessage({
        type: 'request_statistics',
        timestamp: new Date().toISOString()
      })
    }
  }, [isConnected, sendMessage])

  return {
    isConnected,
    subscribeToDevice,
    unsubscribeFromDevice,
    requestStatisticsUpdate
  }
}