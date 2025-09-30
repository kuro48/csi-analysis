'use client'

import React, { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import MainLayout from '@/components/layout/MainLayout'
import { ProtectedPage } from '@/components/auth/AuthGuard'
import DeviceList from '@/components/devices/DeviceList'
import DeviceFilters from '@/components/devices/DeviceFilters'
import CreateDeviceModal from '@/components/devices/CreateDeviceModal'
import { api } from '@/services/api'
import { useDeviceRealtime } from '@/hooks/useDeviceRealtime'

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

interface DeviceFilters {
  status: string
  device_type: string
  location: string
  search: string
  is_active?: boolean
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)

  // フィルター・ページネーション状態
  const [filters, setFilters] = useState<DeviceFilters>({
    status: 'all',
    device_type: 'all',
    location: '',
    search: '',
    is_active: undefined
  })
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalDevices, setTotalDevices] = useState(0)
  const pageSize = 20

  // デバイス統計
  const [statistics, setStatistics] = useState({
    total_devices: 0,
    online_devices: 0,
    offline_devices: 0,
    error_devices: 0,
    by_type: {},
    by_location: {}
  })

  // デバイス一覧取得
  const fetchDevices = async () => {
    try {
      setLoading(true)
      setError('')

      // URLSearchParams用のパラメータを準備
      const paramsObj: Record<string, string> = {
        page: currentPage.toString(),
        page_size: pageSize.toString(),
      }

      // フィルターオブジェクトを文字列に変換して追加
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== '') {
          paramsObj[key] = typeof value === 'boolean' ? value.toString() : value
        }
      })

      const params = new URLSearchParams(paramsObj)

      // undefined値を除外
      Object.keys(params).forEach(key => {
        if (params.get(key) === 'undefined' || params.get(key) === '') {
          params.delete(key)
        }
      })

      const response = await api.devices.list(params)
      setDevices(response.devices)
      setTotalPages(response.total_pages)
      setTotalDevices(response.total)

    } catch (err: any) {
      console.error('Failed to fetch devices:', err)
      setError('デバイス一覧の取得に失敗しました')
    } finally {
      setLoading(false)
    }
  }

  // 統計情報取得
  const fetchStatistics = async () => {
    try {
      const stats = await api.devices.statistics()
      setStatistics(stats)
    } catch (err) {
      console.error('Failed to fetch statistics:', err)
    }
  }

  // 初回読み込み
  useEffect(() => {
    fetchDevices()
    fetchStatistics()
  }, [currentPage, filters])

  // フィルター変更時
  const handleFiltersChange = (newFilters: DeviceFilters) => {
    setFilters(newFilters)
    setCurrentPage(1)
  }


  // デバイス削除成功時
  const handleDeviceDeleted = (deviceId: string) => {
    setDevices(prev => prev.filter(device => device.id !== deviceId))
    fetchStatistics() // 統計を更新
  }

  // リアルタイム更新処理
  const handleDeviceStatusUpdate = useCallback((updatedDevice: Device) => {
    setDevices(prev =>
      prev.map(device =>
        device.device_id === updatedDevice.device_id
          ? { ...device, ...updatedDevice }
          : device
      )
    )
  }, [])

  const handleDeviceCreated = useCallback((newDevice: Device) => {
    setDevices(prev => [newDevice, ...prev])
    setShowCreateModal(false)
    fetchStatistics()
  }, [])

  const handleDeviceUpdated = useCallback((updatedDevice: Device) => {
    setDevices(prev =>
      prev.map(device =>
        device.id === updatedDevice.id
          ? { ...device, ...updatedDevice }
          : device
      )
    )
  }, [])

  const handleDeviceDeletedRealtime = useCallback((deviceId: string) => {
    setDevices(prev => prev.filter(device => device.device_id !== deviceId))
    fetchStatistics()
  }, [])

  const handleStatisticsUpdate = useCallback((newStatistics: any) => {
    setStatistics(newStatistics)
  }, [])

  const handleHeartbeat = useCallback((deviceId: string, heartbeatData: any) => {
    setDevices(prev =>
      prev.map(device =>
        device.device_id === deviceId
          ? {
              ...device,
              status: heartbeatData.status,
              connection_status: heartbeatData.connection_status || 'connected',
              last_seen: heartbeatData.last_seen
            }
          : device
      )
    )
  }, [])

  // WebSocketリアルタイム機能を初期化
  const { isConnected, requestStatisticsUpdate } = useDeviceRealtime({
    onDeviceStatusUpdate: handleDeviceStatusUpdate,
    onDeviceCreated: handleDeviceCreated,
    onDeviceUpdated: handleDeviceUpdated,
    onDeviceDeleted: handleDeviceDeletedRealtime,
    onDeviceStatistics: handleStatisticsUpdate,
    onHeartbeat: handleHeartbeat
  })

  return (
    <ProtectedPage>
      <MainLayout>
        <div className="space-y-6">
          {/* ページヘッダー */}
          <div className="md:flex md:items-center md:justify-between">
            <div className="flex-1 min-w-0">
              <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                デバイス管理
              </h2>
              <p className="mt-1 text-sm text-gray-500">
                CSI呼吸監視デバイスの登録・設定・状態監視
              </p>
            </div>
            <div className="mt-4 flex items-center space-x-3 md:mt-0 md:ml-4">
              {/* WebSocket接続状態インジケーター */}
              <div className="flex items-center space-x-2 text-sm">
                <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
                <span className={isConnected ? 'text-green-600' : 'text-red-600'}>
                  {isConnected ? 'リアルタイム接続中' : '接続切断中'}
                </span>
              </div>
              <button
                onClick={() => setShowCreateModal(true)}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium"
              >
                新しいデバイスを追加
              </button>
            </div>
          </div>

          {/* 統計カード */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">総デバイス数</p>
                  <p className="text-3xl font-semibold text-gray-900">{statistics.total_devices}</p>
                </div>
                <div className="text-3xl">📱</div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">オンライン</p>
                  <p className="text-3xl font-semibold text-green-600">{statistics.online_devices}</p>
                </div>
                <div className="text-3xl">🟢</div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">オフライン</p>
                  <p className="text-3xl font-semibold text-gray-500">{statistics.offline_devices}</p>
                </div>
                <div className="text-3xl">🔴</div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">エラー</p>
                  <p className="text-3xl font-semibold text-red-600">{statistics.error_devices}</p>
                </div>
                <div className="text-3xl">⚠️</div>
              </div>
            </div>
          </div>

          {/* フィルター */}
          <DeviceFilters
            filters={filters}
            onFiltersChange={handleFiltersChange}
            statistics={statistics}
          />

          {/* エラー表示 */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">
              {error}
            </div>
          )}

          {/* デバイス一覧 */}
          <DeviceList
            devices={devices}
            loading={loading}
            currentPage={currentPage}
            totalPages={totalPages}
            totalDevices={totalDevices}
            pageSize={pageSize}
            onPageChange={setCurrentPage}
            onDeviceDeleted={handleDeviceDeleted}
            onRefresh={fetchDevices}
          />

          {/* 新規作成モーダル */}
          {showCreateModal && (
            <CreateDeviceModal
              onClose={() => setShowCreateModal(false)}
              onDeviceCreated={handleDeviceCreated}
            />
          )}
        </div>
      </MainLayout>
    </ProtectedPage>
  )
}