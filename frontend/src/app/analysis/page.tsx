'use client'

import React, { useState, useEffect, useCallback, useMemo } from 'react'
import MainLayout from '@/components/layout/MainLayout'
import { ProtectedPage } from '@/components/auth/AuthGuard'
import BreathingAnalysisChart from '@/components/charts/BreathingAnalysisChart'
import CSIUploadModal from '@/components/data/CSIUploadModal'
import { apiClient } from '@/services/api'
import { useDeviceRealtime } from '@/hooks/useDeviceRealtime'

interface Device {
  id: string
  device_id: string
  device_name: string
  device_type: string
  location?: string
  status: string
}

interface AnalysisData {
  timestamp: string
  value: number | null
}

export default function AnalysisPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('')
  const [breathingData, setBreathingData] = useState<AnalysisData[]>([])
  const [confidenceData, setConfidenceData] = useState<AnalysisData[]>([])
  const [timeRange, setTimeRange] = useState(24) // hours
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  // 統計情報
  const [analysisStats, setAnalysisStats] = useState({
    total_analyses: 0,
    avg_breathing_rate: null as number | null,
    avg_confidence_score: null as number | null,
    latest_analysis: null as string | null
  })

  // デバイス一覧取得
  const fetchDevices = useCallback(async () => {
    try {
      const response = await apiClient.getDevices()
      setDevices(response.devices || [])

      // デフォルトで最初のデバイスを選択
      if (response.devices?.length > 0 && !selectedDeviceId) {
        setSelectedDeviceId(response.devices[0].device_id)
      }
    } catch (err) {
      console.error('Failed to fetch devices:', err)
      setError('デバイス一覧の取得に失敗しました')
    }
  }, [selectedDeviceId])

  // 呼吸解析データ取得
  const fetchBreathingTrends = useCallback(async (deviceId: string, hours: number) => {
    if (!deviceId) return

    setLoading(true)
    setError('')

    try {
      const trends = await apiClient.getBreathingTrends(deviceId, hours)

      setBreathingData(trends.breathing_rate || [])
      setConfidenceData(trends.confidence || [])
      setAnalysisStats({
        total_analyses: trends.data_points || 0,
        avg_breathing_rate: trends.summary?.avg_breathing_rate || null,
        avg_confidence_score: null,
        latest_analysis: trends.timestamps?.length > 0 ? trends.timestamps[trends.timestamps.length - 1] : null
      })
      setLastUpdate(new Date())

    } catch (err: any) {
      console.error('Failed to fetch breathing trends:', err)
      setError('解析データの取得に失敗しました')
      setBreathingData([])
      setConfidenceData([])
    } finally {
      setLoading(false)
    }
  }, [])

  // 初回データ読み込み
  useEffect(() => {
    fetchDevices()
  }, [fetchDevices])

  // デバイス変更時のデータ読み込み
  useEffect(() => {
    if (selectedDeviceId) {
      fetchBreathingTrends(selectedDeviceId, timeRange)
    }
  }, [selectedDeviceId, timeRange, fetchBreathingTrends])

  // リアルタイム更新
  const handleNewBreathingAnalysis = useCallback((deviceId: string, analysisData: any) => {
    if (deviceId === selectedDeviceId) {
      // 新しいデータポイントを追加
      const newBreathingPoint = {
        timestamp: analysisData.analysis_timestamp || new Date().toISOString(),
        value: analysisData.breathing_rate
      }

      const newConfidencePoint = {
        timestamp: analysisData.analysis_timestamp || new Date().toISOString(),
        value: analysisData.confidence_score
      }

      setBreathingData(prev => {
        const updated = [...prev, newBreathingPoint]
        // 最新100ポイントのみ保持
        return updated.slice(-100)
      })

      setConfidenceData(prev => {
        const updated = [...prev, newConfidencePoint]
        return updated.slice(-100)
      })

      setLastUpdate(new Date())
    }
  }, [selectedDeviceId])

  // WebSocketリアルタイム機能
  const { isConnected } = useDeviceRealtime({
    onHeartbeat: handleNewBreathingAnalysis
  })

  const handleDeviceChange = (deviceId: string) => {
    setSelectedDeviceId(deviceId)
  }

  const handleTimeRangeChange = (hours: number) => {
    setTimeRange(hours)
  }

  const handleUploadComplete = (uploadedData: any) => {
    setShowUploadModal(false)

    // アップロード完了後、データを再読み込み
    if (selectedDeviceId) {
      setTimeout(() => {
        fetchBreathingTrends(selectedDeviceId, timeRange)
      }, 1000)
    }
  }

  // selectedDeviceの計算をメモ化
  const selectedDevice = useMemo(() =>
    devices.find(d => d.device_id === selectedDeviceId),
    [devices, selectedDeviceId]
  )

  return (
    <ProtectedPage>
      <MainLayout>
        <div className="space-y-6">
          {/* ページヘッダー */}
          <div className="md:flex md:items-center md:justify-between">
            <div className="flex-1 min-w-0">
              <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                データ解析
              </h2>
              <p className="mt-1 text-sm text-gray-500">
                CSI呼吸解析データのリアルタイム監視と詳細分析
              </p>
            </div>
            <div className="mt-4 flex items-center space-x-3 md:mt-0 md:ml-4">
              {/* WebSocket接続状態 */}
              <div className="flex items-center space-x-2 text-sm">
                <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
                <span className={isConnected ? 'text-green-600' : 'text-red-600'}>
                  {isConnected ? 'リアルタイム更新中' : '接続切断中'}
                </span>
              </div>
              <button
                onClick={() => setShowUploadModal(true)}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium"
              >
                データアップロード
              </button>
            </div>
          </div>

          {/* デバイス選択と時間範囲 */}
          <div className="bg-white rounded-lg shadow p-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  対象デバイス
                </label>
                <select
                  value={selectedDeviceId}
                  onChange={(e) => handleDeviceChange(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="">デバイスを選択</option>
                  {devices.map(device => (
                    <option key={device.id} value={device.device_id}>
                      {device.device_name} ({device.device_id})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  表示期間
                </label>
                <select
                  value={timeRange}
                  onChange={(e) => handleTimeRangeChange(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value={1}>過去1時間</option>
                  <option value={6}>過去6時間</option>
                  <option value={24}>過去24時間</option>
                  <option value={168}>過去1週間</option>
                </select>
              </div>

              <div className="flex items-end">
                <button
                  onClick={() => selectedDeviceId && fetchBreathingTrends(selectedDeviceId, timeRange)}
                  disabled={loading || !selectedDeviceId}
                  className="w-full px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? '読み込み中...' : '更新'}
                </button>
              </div>
            </div>

            {selectedDevice && (
              <div className="mt-4 p-3 bg-blue-50 rounded-md">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium text-blue-900">
                      {selectedDevice.device_name}
                    </span>
                    <span className="ml-2 text-sm text-blue-700">
                      ({selectedDevice.location || '場所未設定'})
                    </span>
                  </div>
                  <div className="flex items-center space-x-3 text-sm">
                    <div className={`flex items-center space-x-1 ${
                      selectedDevice.status === 'online' ? 'text-green-700' : 'text-gray-700'
                    }`}>
                      <div className={`w-2 h-2 rounded-full ${
                        selectedDevice.status === 'online' ? 'bg-green-500' : 'bg-gray-500'
                      }`}></div>
                      <span>{selectedDevice.status === 'online' ? 'オンライン' : 'オフライン'}</span>
                    </div>
                    {lastUpdate && (
                      <span className="text-blue-600">
                        最終更新: {lastUpdate.toLocaleTimeString()}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* エラー表示 */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">
              {error}
            </div>
          )}

          {/* 統計サマリー */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">総解析回数</p>
                  <p className="text-3xl font-semibold text-gray-900">{analysisStats.total_analyses}</p>
                </div>
                <div className="text-3xl">📊</div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">平均呼吸数</p>
                  <p className="text-3xl font-semibold text-blue-600">
                    {analysisStats.avg_breathing_rate ? `${analysisStats.avg_breathing_rate.toFixed(1)}` : 'N/A'}
                  </p>
                  <p className="text-xs text-gray-500">回/分</p>
                </div>
                <div className="text-3xl">💨</div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">データ品質</p>
                  <p className="text-3xl font-semibold text-green-600">
                    {analysisStats.avg_confidence_score ? `${(analysisStats.avg_confidence_score * 100).toFixed(0)}%` : 'N/A'}
                  </p>
                </div>
                <div className="text-3xl">✅</div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">最新解析</p>
                  <p className="text-sm font-semibold text-gray-900">
                    {analysisStats.latest_analysis
                      ? new Date(analysisStats.latest_analysis).toLocaleString()
                      : 'N/A'
                    }
                  </p>
                </div>
                <div className="text-3xl">🕒</div>
              </div>
            </div>
          </div>

          {/* メインチャート */}
          <BreathingAnalysisChart
            breathingData={breathingData}
            confidenceData={confidenceData}
            title={`呼吸解析トレンド - ${selectedDevice?.device_name || 'デバイス未選択'}`}
            height={400}
            showConfidence={true}
          />

          {/* アップロードモーダル */}
          {showUploadModal && (
            <CSIUploadModal
              deviceId={selectedDeviceId}
              onClose={() => setShowUploadModal(false)}
              onUploadComplete={handleUploadComplete}
            />
          )}
        </div>
      </MainLayout>
    </ProtectedPage>
  )
}