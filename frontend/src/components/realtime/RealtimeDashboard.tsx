'use client'

import React, { useState, useEffect } from 'react'
import { useRealTimeData } from '@/hooks/useRealTimeData'
import RealtimeChart, { BreathingRateChart, ConfidenceChart } from '@/components/charts/RealtimeChart'

export default function RealtimeDashboard() {
  const { data, connectionStatus } = useRealTimeData()
  const [selectedDevice, setSelectedDevice] = useState<string>('')

  // 呼吸解析データをチャート用に変換
  const [breathingData, setBreathingData] = useState<Array<{
    timestamp: string
    value: number
    formatted_time: string
  }>>([])

  const [confidenceData, setConfidenceData] = useState<Array<{
    timestamp: string
    value: number
    formatted_time: string
  }>>([])

  // データ更新時の処理
  useEffect(() => {
    if (selectedDevice && data.breathingAnalyses[selectedDevice]) {
      const analysis = data.breathingAnalyses[selectedDevice]

      const newBreathingPoint = {
        timestamp: analysis.timestamp,
        value: analysis.breathing_rate,
        formatted_time: new Date(analysis.timestamp).toLocaleTimeString(),
      }

      const newConfidencePoint = {
        timestamp: analysis.timestamp,
        value: analysis.confidence,
        formatted_time: new Date(analysis.timestamp).toLocaleTimeString(),
      }

      setBreathingData(prev => [...prev.slice(-29), newBreathingPoint])
      setConfidenceData(prev => [...prev.slice(-29), newConfidencePoint])
    }
  }, [data.breathingAnalyses, selectedDevice])

  // 接続状態のスタイル
  const getConnectionStatusColor = () => {
    switch (connectionStatus) {
      case 'Open':
        return 'bg-green-500'
      case 'Connecting':
        return 'bg-yellow-500'
      case 'Closing':
      case 'Closed':
        return 'bg-red-500'
      default:
        return 'bg-gray-500'
    }
  }

  const deviceList = Object.keys(data.deviceStatuses)

  // 初期デバイス選択
  useEffect(() => {
    if (deviceList.length > 0 && !selectedDevice) {
      setSelectedDevice(deviceList[0])
    }
  }, [deviceList, selectedDevice])

  return (
    <div className="space-y-6">
      {/* 接続状態とコントロール */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2">
              <div className={`w-3 h-3 rounded-full ${getConnectionStatusColor()}`}></div>
              <span className="text-sm font-medium">
                WebSocket: {connectionStatus}
              </span>
            </div>
            <div className="text-sm text-gray-500">
              接続デバイス数: {deviceList.length}
            </div>
          </div>

          {/* デバイス選択 */}
          <div className="flex items-center space-x-4">
            <label htmlFor="device-select" className="text-sm font-medium text-gray-700">
              監視デバイス:
            </label>
            <select
              id="device-select"
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {deviceList.map((deviceId) => (
                <option key={deviceId} value={deviceId}>
                  {deviceId}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* リアルタイムデバイス状態 */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">リアルタイムデバイス状態</h3>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(data.deviceStatuses).map(([deviceId, status]) => (
              <div
                key={deviceId}
                className={`p-4 rounded-lg border ${
                  status.status === 'online'
                    ? 'border-green-200 bg-green-50'
                    : status.status === 'error'
                    ? 'border-red-200 bg-red-50'
                    : 'border-gray-200 bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-medium text-gray-900">{deviceId}</h4>
                  <div className={`w-3 h-3 rounded-full ${
                    status.status === 'online' ? 'bg-green-500' :
                    status.status === 'error' ? 'bg-red-500' : 'bg-gray-500'
                  }`}></div>
                </div>
                <p className="text-sm text-gray-600">
                  状態: {status.status}
                </p>
                <p className="text-xs text-gray-500">
                  最終確認: {new Date(status.last_seen).toLocaleTimeString()}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* リアルタイムチャート */}
      {selectedDevice && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <BreathingRateChart
            deviceId={selectedDevice}
            data={breathingData}
          />
          <ConfidenceChart
            deviceId={selectedDevice}
            data={confidenceData}
          />
        </div>
      )}

      {/* 最新の呼吸解析データ */}
      {selectedDevice && data.breathingAnalyses[selectedDevice] && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            最新の呼吸解析データ - {selectedDevice}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-blue-50 p-4 rounded-lg">
              <p className="text-sm font-medium text-blue-600">呼吸数</p>
              <p className="text-2xl font-bold text-blue-900">
                {data.breathingAnalyses[selectedDevice].breathing_rate} bpm
              </p>
            </div>
            <div className="bg-green-50 p-4 rounded-lg">
              <p className="text-sm font-medium text-green-600">信頼度</p>
              <p className="text-2xl font-bold text-green-900">
                {data.breathingAnalyses[selectedDevice].confidence}%
              </p>
            </div>
            <div className="bg-gray-50 p-4 rounded-lg">
              <p className="text-sm font-medium text-gray-600">更新時刻</p>
              <p className="text-2xl font-bold text-gray-900">
                {new Date(data.breathingAnalyses[selectedDevice].timestamp).toLocaleTimeString()}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* システム通知 */}
      {data.systemNotifications.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">システム通知</h3>
          <div className="space-y-3">
            {data.systemNotifications.slice(0, 5).map((notification) => (
              <div
                key={notification.id}
                className={`p-3 rounded-md border-l-4 ${
                  notification.type === 'error'
                    ? 'border-red-500 bg-red-50'
                    : notification.type === 'warning'
                    ? 'border-yellow-500 bg-yellow-50'
                    : notification.type === 'success'
                    ? 'border-green-500 bg-green-50'
                    : 'border-blue-500 bg-blue-50'
                }`}
              >
                <div className="flex justify-between items-start">
                  <p className="text-sm font-medium text-gray-900">
                    {notification.message}
                  </p>
                  <p className="text-xs text-gray-500">
                    {new Date(notification.timestamp).toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* デバッグ情報（開発時のみ表示） */}
      {process.env.NODE_ENV === 'development' && (
        <div className="bg-gray-50 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">デバッグ情報</h4>
          <pre className="text-xs text-gray-600 overflow-auto">
            {JSON.stringify(
              {
                connectionStatus,
                deviceCount: Object.keys(data.deviceStatuses).length,
                analysisCount: Object.keys(data.breathingAnalyses).length,
                notificationCount: data.systemNotifications.length,
              },
              null,
              2
            )}
          </pre>
        </div>
      )}
    </div>
  )
}