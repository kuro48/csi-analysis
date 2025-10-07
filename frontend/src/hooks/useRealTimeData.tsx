'use client'

import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react'
import { usePathname } from 'next/navigation'
import { useWebSocket } from './useWebSocket'

interface RealtimeData {
  deviceStatuses: Record<string, DeviceStatus>
  breathingAnalyses: Record<string, BreathingAnalysis>
  systemNotifications: SystemNotification[]
}

interface DeviceStatus {
  device_id: string
  status: 'online' | 'offline' | 'error'
  last_seen: string
  data?: any
}

interface BreathingAnalysis {
  device_id: string
  breathing_rate: number
  confidence: number
  timestamp: string
  data?: any
}

interface SystemNotification {
  id: string
  type: 'info' | 'warning' | 'error' | 'success'
  message: string
  timestamp: string
}

interface RealtimeContextType {
  data: RealtimeData
  connectionStatus: 'Connecting' | 'Open' | 'Closing' | 'Closed'
  subscribe: (channel: string) => boolean
  unsubscribe: (channel: string) => boolean
  sendMessage: (message: any) => boolean
}

const RealtimeContext = createContext<RealtimeContextType | null>(null)

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<RealtimeData>({
    deviceStatuses: {},
    breathingAnalyses: {},
    systemNotifications: [],
  })

  // usePathnameを安全に使用
  let pathname = '/'
  try {
    if (typeof window !== 'undefined') {
      pathname = usePathname()
    }
  } catch (error) {
    console.warn('RealtimeProvider: usePathname not available, defaulting to /', error)
    pathname = typeof window !== 'undefined' ? window.location.pathname : '/'
  }

  // WebSocket接続が必要なページパスを定義
  const realtimePages = ['/dashboard', '/devices', '/analysis']
  const shouldConnect = realtimePages.some(page => pathname.startsWith(page))

  // Debug logging for development only
  if (process.env.NODE_ENV === 'development') {
    console.log(`Page: ${pathname}, Should connect WebSocket: ${shouldConnect}`)
  }

  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/api/v2/ws/realtime'

  const { connectionStatus, sendMessage, subscribe, unsubscribe } = useWebSocket({
    url: wsUrl,
    enabled: shouldConnect, // 対象ページでのみ接続
    shouldReconnect: shouldConnect, // ページによって再接続制御
    onMessage: (message) => {
      handleRealtimeMessage(message)
    },
    onOpen: () => {
      console.log('WebSocket connected on', pathname)
      // 基本チャンネルに自動購読
      subscribe('dashboard')
    },
    onClose: () => {
      console.log('WebSocket disconnected from', pathname)
    },
    onError: (error) => {
      console.error('WebSocket error on', pathname, ':', error)
    },
  })

  const handleRealtimeMessage = useCallback((message: any) => {
    console.log('Received WebSocket message:', message)

    switch (message.type) {
      case 'device_status_update':
        setData((prev) => ({
          ...prev,
          deviceStatuses: {
            ...prev.deviceStatuses,
            [message.device_id]: {
              device_id: message.device_id,
              status: message.data.status || 'online',
              last_seen: message.timestamp,
              data: message.data,
            },
          },
        }))
        break

      case 'breathing_analysis_update':
        setData((prev) => ({
          ...prev,
          breathingAnalyses: {
            ...prev.breathingAnalyses,
            [message.device_id]: {
              device_id: message.device_id,
              breathing_rate: message.data.breathing_rate || 0,
              confidence: message.data.confidence || 0,
              timestamp: message.timestamp,
              data: message.data,
            },
          },
        }))
        break

      case 'system_notification':
        const notification: SystemNotification = {
          id: `${Date.now()}-${Math.random()}`,
          type: message.data.type || 'info',
          message: message.data.message || 'Unknown notification',
          timestamp: message.timestamp,
        }
        setData((prev) => ({
          ...prev,
          systemNotifications: [notification, ...prev.systemNotifications.slice(0, 99)], // 最大100件
        }))
        break

      case 'connection_established':
        console.log('Connection established:', message)
        break

      case 'subscribed':
        console.log(`Subscribed to channel: ${message.channel}`)
        break

      case 'unsubscribed':
        console.log(`Unsubscribed from channel: ${message.channel}`)
        break

      case 'pong':
        console.log('Pong received')
        break

      case 'error':
        console.error('WebSocket server error:', message.message)
        break

      default:
        console.log('Unknown message type:', message.type)
    }
  }, []) // useCallbackの依存関係配列を追加

  const contextValue: RealtimeContextType = {
    data,
    connectionStatus,
    subscribe,
    unsubscribe,
    sendMessage,
  }

  return (
    <RealtimeContext.Provider value={contextValue}>
      {children}
    </RealtimeContext.Provider>
  )
}

export function useRealTimeData(): RealtimeContextType {
  const context = useContext(RealtimeContext)
  if (!context) {
    throw new Error('useRealTimeData must be used within a RealtimeProvider')
  }
  return context
}

// 特定デバイスの監視用フック
export function useDeviceRealtime(deviceId: string) {
  const { data, subscribe, unsubscribe } = useRealTimeData()

  useEffect(() => {
    subscribe(`device_${deviceId}`)
    return () => {
      unsubscribe(`device_${deviceId}`)
    }
  }, [deviceId, subscribe, unsubscribe])

  return {
    deviceStatus: data.deviceStatuses[deviceId],
    breathingAnalysis: data.breathingAnalyses[deviceId],
  }
}