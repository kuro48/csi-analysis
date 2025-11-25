'use client'

import { useEffect, useState, useRef, useCallback } from 'react'
import { useWebSocket } from './useWebSocket'

interface CSIAnalysisData {
  timestamp: string
  breathing_rate: number
  breathing_amplitude: number
  breathing_confidence: number
  signal_quality: number
  motion_detected: boolean
  anomaly_score: number
  raw_signal: number[]
}

interface UseRealtimeCSIOptions {
  deviceId: string
  enabled?: boolean
  maxDataPoints?: number
}

interface UseRealtimeCSIReturn {
  isConnected: boolean
  currentData: CSIAnalysisData | null
  historicalData: CSIAnalysisData[]
  connectionStatus: string
  startMonitoring: () => void
  stopMonitoring: () => void
  clearData: () => void
}

export function useRealtimeCSI({
  deviceId,
  enabled = true,
  maxDataPoints = 100
}: UseRealtimeCSIOptions): UseRealtimeCSIReturn {
  const [currentData, setCurrentData] = useState<CSIAnalysisData | null>(null)
  const [historicalData, setHistoricalData] = useState<CSIAnalysisData[]>([])
  const [isMonitoring, setIsMonitoring] = useState(enabled)

  const historicalDataRef = useRef<CSIAnalysisData[]>([])

  // WebSocket接続設定
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const wsUrl = apiUrl.replace(/^https?:/, window?.location?.protocol === 'https:' ? 'wss:' : 'ws:') + '/api/v2/ws'

  const {
    connectionStatus,
    subscribe,
    unsubscribe,
    sendMessage,
    lastMessage
  } = useWebSocket({
    url: wsUrl,
    enabled: isMonitoring,
    shouldReconnect: true,
    reconnectInterval: 3000,
    maxReconnectAttempts: 5,
    onOpen: () => {
      if (isMonitoring) {
        // 必要なチャンネルに購読
        subscribe(`realtime_csi_${deviceId}`)
        subscribe('realtime_monitoring')
        subscribe(`device_${deviceId}`)
      }
    },
    onMessage: (message) => {
      if (message.type === 'csi_analysis_realtime' && message.device_id === deviceId) {
        handleCSIAnalysisMessage(message.data)
      }
    },
    onError: (error) => {
      console.error('リアルタイムCSI WebSocketエラー:', error)
    },
    onClose: (event) => {
      // WebSocket closed
    }
  })

  const handleCSIAnalysisMessage = useCallback((data: any) => {
    const analysisData: CSIAnalysisData = {
      timestamp: data.timestamp,
      breathing_rate: data.breathing_rate || 0,
      breathing_amplitude: data.breathing_amplitude || 0,
      breathing_confidence: data.breathing_confidence || 0,
      signal_quality: data.signal_quality || 0,
      motion_detected: data.motion_detected || false,
      anomaly_score: data.anomaly_score || 0,
      raw_signal: data.raw_signal || []
    }

    setCurrentData(analysisData)

    // 履歴データに追加
    historicalDataRef.current = [...historicalDataRef.current, analysisData].slice(-maxDataPoints)
    setHistoricalData([...historicalDataRef.current])
  }, [maxDataPoints])

  const startMonitoring = useCallback(() => {
    setIsMonitoring(true)
  }, [])

  const stopMonitoring = useCallback(() => {
    setIsMonitoring(false)
    if (connectionStatus === 'Open') {
      unsubscribe(`realtime_csi_${deviceId}`)
      unsubscribe('realtime_monitoring')
      unsubscribe(`device_${deviceId}`)
    }
  }, [connectionStatus, deviceId, unsubscribe])

  const clearData = useCallback(() => {
    setCurrentData(null)
    setHistoricalData([])
    historicalDataRef.current = []
  }, [])

  // チャンネル購読管理
  useEffect(() => {
    if (isMonitoring && connectionStatus === 'Open') {
      subscribe(`realtime_csi_${deviceId}`)
      subscribe('realtime_monitoring')
      subscribe(`device_${deviceId}`)
    }

    return () => {
      if (connectionStatus === 'Open') {
        unsubscribe(`realtime_csi_${deviceId}`)
        unsubscribe('realtime_monitoring')
        unsubscribe(`device_${deviceId}`)
      }
    }
  }, [isMonitoring, connectionStatus, deviceId, subscribe, unsubscribe])

  return {
    isConnected: connectionStatus === 'Open',
    currentData,
    historicalData,
    connectionStatus,
    startMonitoring,
    stopMonitoring,
    clearData
  }
}