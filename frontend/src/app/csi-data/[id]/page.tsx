'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiClient } from '@/services/api'
import CSIChart from '@/components/visualization/CSIChart'

interface CSIData {
  id: string
  device_id: string
  session_id?: string
  file_path: string
  file_size: number
  status: string
  created_at: string
  updated_at: string
  raw_data?: any
  processed_data?: any
}

interface CSIVisualizationData {
  csi_data_id: string
  subcarrier_data: Record<string, {
    timestamps: number[]
    amplitudes: number[]
    phases: number[]
  }>
  summary: {
    n_subcarriers: number
    n_samples: number
    time_range: {
      start: number
      end: number
    }
  }
  metadata: {
    total_subcarriers: number
    displayed_subcarriers: number
    time_window_applied: boolean
    device_id: string
  }
}

export default function CSIDataDetailPage() {
  const params = useParams()
  const router = useRouter()
  const csiDataId = params.id as string

  const [csiData, setCsiData] = useState<CSIData | null>(null)
  const [visualizationData, setVisualizationData] = useState<CSIVisualizationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [subcarrierLimit, setSubcarrierLimit] = useState(10)
  const [timeWindow, setTimeWindow] = useState<number | null>(null)

  useEffect(() => {
    if (csiDataId) {
      loadCSIData()
    }
  }, [csiDataId])

  useEffect(() => {
    if (csiData && csiData.status === 'processed') {
      loadVisualizationData()
    }
  }, [csiData, subcarrierLimit, timeWindow])

  const loadCSIData = async () => {
    try {
      setLoading(true)
      const response = await apiClient.get(`/csi-data/${csiDataId}`)
      setCsiData(response as CSIData)
    } catch (err: any) {
      console.error('Failed to load CSI data:', err)
      setError(err.response?.data?.detail || 'CSIデータの読み込みに失敗しました')
    } finally {
      setLoading(false)
    }
  }

  const loadVisualizationData = async () => {
    if (!csiData) return

    try {
      const params = new URLSearchParams({
        subcarrier_limit: subcarrierLimit.toString()
      })

      if (timeWindow) {
        params.append('time_window', timeWindow.toString())
      }

      const response = await apiClient.get(
        `/csi-data/${csiDataId}/visualization?${params}`
      )
      setVisualizationData(response as CSIVisualizationData)
    } catch (err: any) {
      console.error('Failed to load visualization data:', err)
      setError(err.response?.data?.detail || '可視化データの読み込みに失敗しました')
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const getStatusBadge = (status: string) => {
    const statusColors = {
      'received': 'bg-yellow-100 text-yellow-800',
      'processing': 'bg-blue-100 text-blue-800',
      'processed': 'bg-green-100 text-green-800',
      'error': 'bg-red-100 text-red-800'
    }

    const statusLabels = {
      'received': '受信済み',
      'processing': '処理中',
      'processed': '処理完了',
      'error': 'エラー'
    }

    return (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
        statusColors[status as keyof typeof statusColors] || 'bg-gray-100 text-gray-800'
      }`}>
        {statusLabels[status as keyof typeof statusLabels] || status}
      </span>
    )
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">CSIデータを読み込み中...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="text-red-600 text-xl mb-4">エラー</div>
          <p className="text-gray-600 mb-4">{error}</p>
          <button
            onClick={() => router.back()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            戻る
          </button>
        </div>
      </div>
    )
  }

  if (!csiData) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600">CSIデータが見つかりません</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ヘッダー */}
      <div className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="py-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <button
                  onClick={() => router.back()}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
                <div>
                  <h1 className="text-2xl font-bold text-gray-900">CSIデータ詳細</h1>
                  <p className="text-sm text-gray-500">ID: {csiData.id}</p>
                </div>
              </div>
              {getStatusBadge(csiData.status)}
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* 基本情報 */}
        <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">基本情報</h2>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-medium text-gray-500">デバイスID</dt>
              <dd className="mt-1 text-sm text-gray-900">{csiData.device_id}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">セッションID</dt>
              <dd className="mt-1 text-sm text-gray-900">{csiData.session_id || '未設定'}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">ファイルサイズ</dt>
              <dd className="mt-1 text-sm text-gray-900">{formatFileSize(csiData.file_size)}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">アップロード日時</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {new Date(csiData.created_at).toLocaleString('ja-JP')}
              </dd>
            </div>
          </dl>
        </div>

        {/* 処理未完了の場合のメッセージ */}
        {csiData.status !== 'processed' && (
          <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 mb-6">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-yellow-700">
                  {csiData.status === 'received' && 'CSIデータの処理が完了していません。PCAPファイルの解析には時間がかかる場合があります。'}
                  {csiData.status === 'processing' && 'CSIデータを処理中です。しばらくお待ちください。'}
                  {csiData.status === 'error' && 'CSIデータの処理中にエラーが発生しました。'}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* 可視化設定 */}
        {csiData.status === 'processed' && (
          <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
            <h2 className="text-lg font-medium text-gray-900 mb-4">表示設定</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  表示サブキャリア数
                </label>
                <select
                  value={subcarrierLimit}
                  onChange={(e) => setSubcarrierLimit(Number(e.target.value))}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value={5}>5個</option>
                  <option value={10}>10個</option>
                  <option value={20}>20個</option>
                  <option value={32}>32個</option>
                  <option value={64}>64個（全て）</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  時間窓（秒）
                </label>
                <select
                  value={timeWindow || ''}
                  onChange={(e) => setTimeWindow(e.target.value ? Number(e.target.value) : null)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="">全時間</option>
                  <option value={30}>30秒</option>
                  <option value={60}>1分</option>
                  <option value={300}>5分</option>
                  <option value={600}>10分</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* CSIチャート */}
        {visualizationData && (
          <CSIChart data={visualizationData} className="mb-6" />
        )}
      </div>
    </div>
  )
}