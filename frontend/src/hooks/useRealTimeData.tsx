'use client'

import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react'
import { usePathname } from 'next/navigation'
import { useWebSocket, WebSocketMessage } from './useWebSocket'

interface RealtimeData {
  deviceStatuses: Record<string, DeviceStatus>
  breathingAnalyses: Record<string, BreathingAnalysis>
  systemNotifications: SystemNotification[]
}

interface DeviceStatus {
  device_id: string
  status: 'online' | 'offline' | 'error'
  last_seen: string
  data?: Record<string, unknown>
}

interface BreathingAnalysis {
  device_id: string
  breathing_rate: number
  confidence: number
  timestamp: string
  data?: Record<string, unknown>
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
  sendMessage: (message: WebSocketMessage) => boolean
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
      // 基本チャンネルに自動購読
      subscribe('dashboard')
    },
    onClose: () => {
      // WebSocket disconnected
    },
    onError: (error) => {
      console.error('WebSocket error on', pathname, ':', error)
    },
  })

  const handleRealtimeMessage = useCallback((message: WebSocketMessage) => {
    const deviceId = message.device_id as string | undefined
    const timestamp = message.timestamp as string | undefined
    const msgData = message.data as Record<string, unknown> | undefined

    switch (message.type) {
      case 'device_status_update':
        if (deviceId) {
          setData((prev) => ({
            ...prev,
            deviceStatuses: {
              ...prev.deviceStatuses,
              [deviceId]: {
                device_id: deviceId,
                status: (msgData?.status as DeviceStatus['status']) || 'online',
                last_seen: timestamp ?? '',
                data: msgData,
              },
            },
          }))
        }
        break

      case 'breathing_analysis_update':
        if (deviceId) {
          setData((prev) => ({
            ...prev,
            breathingAnalyses: {
              ...prev.breathingAnalyses,
              [deviceId]: {
                device_id: deviceId,
                breathing_rate: (msgData?.breathing_rate as number) || 0,
                confidence: (msgData?.confidence as number) || 0,
                timestamp: timestamp ?? '',
                data: msgData,
              },
            },
          }))
        }
        break

      case 'system_notification':
        const notification: SystemNotification = {
          id: `${Date.now()}-${Math.random()}`,
          type: (msgData?.type as SystemNotification['type']) || 'info',
          message: (msgData?.message as string) || 'Unknown notification',
          timestamp: timestamp ?? '',
        }
        setData((prev) => ({
          ...prev,
          systemNotifications: [notification, ...prev.systemNotifications.slice(0, 99)], // 最大100件
        }))
        break

      case 'connection_established':
        break

      case 'subscribed':
        break

      case 'unsubscribed':
        break

      case 'pong':
        break

      case 'error':
        console.error('WebSocket server error:', message.message)
        break

      default:
        break
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