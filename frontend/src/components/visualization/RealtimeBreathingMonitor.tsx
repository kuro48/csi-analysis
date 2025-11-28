'use client'

import React, { useState, useEffect, useRef } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Play, Pause, Square } from 'lucide-react'
import { useRealtimeCSI } from '@/hooks/useRealtimeCSI'

interface BreathingData {
  timestamp: string
  breathing_rate: number
  breathing_amplitude: number
  breathing_confidence: number
  signal_quality: number
  motion_detected: boolean
  anomaly_score: number
  raw_signal: number[]
}

interface ChartDataPoint {
  time: string
  breathingRate: number
  amplitude: number
  confidence: number
  signalQuality: number
}

interface RealtimeBreathingMonitorProps {
  deviceId: string
  autoStart?: boolean
  maxDataPoints?: number
}

export default function RealtimeBreathingMonitor({
  deviceId,
  autoStart = true,
  maxDataPoints = 100
}: RealtimeBreathingMonitorProps) {
  const [chartData, setChartData] = useState<ChartDataPoint[]>([])
  const chartDataRef = useRef<ChartDataPoint[]>([])

  // リアルタイムCSIフックを使用
  const {
    isConnected,
    currentData: breathingData,
    historicalData,
    connectionStatus,
    startMonitoring,
    stopMonitoring,
    clearData
  } = useRealtimeCSI({
    deviceId,
    enabled: autoStart,
    maxDataPoints
  })

  // 履歴データをチャート用に変換
  useEffect(() => {
    const newChartData = historicalData.map(data => ({
      time: new Date(data.timestamp).toLocaleTimeString(),
      breathingRate: data.breathing_rate,
      amplitude: data.breathing_amplitude,
      confidence: data.breathing_confidence,
      signalQuality: data.signal_quality
    }))

    setChartData(newChartData)
  }, [historicalData])

  const handleStartMonitoring = () => {
    startMonitoring()
  }

  const handlePauseMonitoring = () => {
    stopMonitoring()
  }

  const handleStopMonitoring = () => {
    stopMonitoring()
    clearData()
    setChartData([])
  }

  const getBreathingRateStatus = (rate: number) => {
    if (rate < 12) return { status: 'low', color: 'bg-blue-500' }
    if (rate > 20) return { status: 'high', color: 'bg-red-500' }
    return { status: 'normal', color: 'bg-green-500' }
  }

  const getConfidenceColor = (confidence: number) => {
    if (confidence > 0.8) return 'text-green-600'
    if (confidence > 0.5) return 'text-yellow-600'
    return 'text-red-600'
  }

  return (
    <div className="space-y-4">
      {/* コントロールパネル */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>リアルタイム呼吸監視 - {deviceId}</CardTitle>
            <div className="flex items-center space-x-2">
              <Badge variant={connectionStatus === 'Open' ? 'default' : 'error'}>
                {connectionStatus === 'Open' ? '接続中' : '切断'}
              </Badge>
              <div className="flex space-x-1">
                <Button
                  size="sm"
                  onClick={handleStartMonitoring}
                  disabled={!isConnected}
                  className="flex items-center space-x-1"
                >
                  <Play className="w-4 h-4" />
                  <span>開始</span>
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handlePauseMonitoring}
                  disabled={!isConnected}
                  className="flex items-center space-x-1"
                >
                  <Pause className="w-4 h-4" />
                  <span>一時停止</span>
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={handleStopMonitoring}
                  disabled={!isConnected}
                  className="flex items-center space-x-1"
                >
                  <Square className="w-4 h-4" />
                  <span>停止</span>
                </Button>
              </div>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* 現在の状態表示 */}
      {breathingData && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="text-center">
                <div className="text-2xl font-bold">
                  {breathingData.breathing_rate.toFixed(1)}
                </div>
                <div className="text-sm text-gray-500">回/分</div>
                <Badge className={getBreathingRateStatus(breathingData.breathing_rate).color}>
                  {getBreathingRateStatus(breathingData.breathing_rate).status}
                </Badge>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="text-center">
                <div className="text-xl font-bold">
                  {(breathingData.breathing_confidence * 100).toFixed(1)}%
                </div>
                <div className="text-sm text-gray-500">信頼度</div>
                <div className={`text-sm font-medium ${getConfidenceColor(breathingData.breathing_confidence)}`}>
                  {breathingData.breathing_confidence > 0.8 ? '高' :
                   breathingData.breathing_confidence > 0.5 ? '中' : '低'}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="text-center">
                <div className="text-xl font-bold">
                  {(breathingData.signal_quality * 100).toFixed(1)}%
                </div>
                <div className="text-sm text-gray-500">信号品質</div>
                <Badge variant={breathingData.motion_detected ? 'error' : 'default'}>
                  {breathingData.motion_detected ? '動作検出' : '安定'}
                </Badge>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="text-center">
                <div className="text-xl font-bold">
                  {(breathingData.anomaly_score * 100).toFixed(1)}%
                </div>
                <div className="text-sm text-gray-500">異常スコア</div>
                <Badge variant={breathingData.anomaly_score > 0.5 ? 'error' : 'default'}>
                  {breathingData.anomaly_score > 0.5 ? '異常' : '正常'}
                </Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* 呼吸数チャート */}
      <Card>
        <CardHeader>
          <CardTitle>呼吸数推移</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="time"
                  interval="preserveStartEnd"
                  tick={{ fontSize: 12 }}
                />
                <YAxis
                  domain={[8, 30]}
                  tick={{ fontSize: 12 }}
                />
                <Tooltip
                  formatter={(value, name) => [
                    typeof value === 'number' ? value.toFixed(1) : value,
                    name === 'breathingRate' ? '呼吸数' : name
                  ]}
                />
                <ReferenceLine y={12} stroke="#3b82f6" strokeDasharray="5 5" label="最低正常値" />
                <ReferenceLine y={20} stroke="#ef4444" strokeDasharray="5 5" label="最高正常値" />
                <Line
                  type="monotone"
                  dataKey="breathingRate"
                  stroke="#8884d8"
                  strokeWidth={2}
                  dot={false}
                  name="呼吸数"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* 信頼度・品質チャート */}
      <Card>
        <CardHeader>
          <CardTitle>信号品質・信頼度</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="time"
                  interval="preserveStartEnd"
                  tick={{ fontSize: 12 }}
                />
                <YAxis
                  domain={[0, 1]}
                  tick={{ fontSize: 12 }}
                />
                <Tooltip
                  formatter={(value, name) => [
                    typeof value === 'number' ? (value * 100).toFixed(1) + '%' : value,
                    name === 'confidence' ? '信頼度' :
                    name === 'signalQuality' ? '信号品質' : name
                  ]}
                />
                <Line
                  type="monotone"
                  dataKey="confidence"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                  name="信頼度"
                />
                <Line
                  type="monotone"
                  dataKey="signalQuality"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={false}
                  name="信号品質"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}