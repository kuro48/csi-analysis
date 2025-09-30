'use client'

import React, { useState } from 'react'
import { format } from 'date-fns'
import { ja } from 'date-fns/locale'
import { api } from '@/services/api'

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

interface DeviceListProps {
  devices: Device[]
  loading: boolean
  currentPage: number
  totalPages: number
  totalDevices: number
  pageSize: number
  onPageChange: (page: number) => void
  onDeviceDeleted: (deviceId: string) => void
  onRefresh: () => void
}

export default function DeviceList({
  devices,
  loading,
  currentPage,
  totalPages,
  totalDevices,
  pageSize,
  onPageChange,
  onDeviceDeleted,
  onRefresh
}: DeviceListProps) {
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  // 状態インジケーターの色とテキスト
  const getStatusDisplay = (status: string, connectionStatus: string) => {
    switch (status) {
      case 'online':
        return {
          color: 'bg-green-500',
          text: 'オンライン',
          textColor: 'text-green-700'
        }
      case 'offline':
        return {
          color: 'bg-gray-500',
          text: 'オフライン',
          textColor: 'text-gray-700'
        }
      case 'error':
        return {
          color: 'bg-red-500',
          text: 'エラー',
          textColor: 'text-red-700'
        }
      case 'maintenance':
        return {
          color: 'bg-yellow-500',
          text: 'メンテナンス',
          textColor: 'text-yellow-700'
        }
      default:
        return {
          color: 'bg-gray-400',
          text: '不明',
          textColor: 'text-gray-700'
        }
    }
  }

  // デバイスタイプの表示名
  const getDeviceTypeDisplay = (deviceType: string) => {
    switch (deviceType) {
      case 'raspberry_pi':
        return 'Raspberry Pi'
      case 'esp32':
        return 'ESP32'
      default:
        return deviceType
    }
  }

  // デバイス削除
  const handleDeleteDevice = async () => {
    if (!selectedDevice) return

    try {
      await api.devices.delete(selectedDevice.id)
      onDeviceDeleted(selectedDevice.id)
      setShowDeleteConfirm(false)
      setSelectedDevice(null)
    } catch (error) {
      console.error('Failed to delete device:', error)
    }
  }

  // ページネーションボタン
  const renderPagination = () => {
    const pages = []
    const maxPagesToShow = 5
    const startPage = Math.max(1, currentPage - Math.floor(maxPagesToShow / 2))
    const endPage = Math.min(totalPages, startPage + maxPagesToShow - 1)

    if (startPage > 1) {
      pages.push(
        <button
          key={1}
          onClick={() => onPageChange(1)}
          className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
        >
          1
        </button>
      )
      if (startPage > 2) {
        pages.push(
          <span key="ellipsis1" className="px-3 py-2 text-sm font-medium text-gray-700">
            ...
          </span>
        )
      }
    }

    for (let i = startPage; i <= endPage; i++) {
      pages.push(
        <button
          key={i}
          onClick={() => onPageChange(i)}
          className={`px-3 py-2 text-sm font-medium border rounded-md ${
            i === currentPage
              ? 'text-blue-600 bg-blue-50 border-blue-300'
              : 'text-gray-700 bg-white border-gray-300 hover:bg-gray-50'
          }`}
        >
          {i}
        </button>
      )
    }

    if (endPage < totalPages) {
      if (endPage < totalPages - 1) {
        pages.push(
          <span key="ellipsis2" className="px-3 py-2 text-sm font-medium text-gray-700">
            ...
          </span>
        )
      }
      pages.push(
        <button
          key={totalPages}
          onClick={() => onPageChange(totalPages)}
          className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
        >
          {totalPages}
        </button>
      )
    }

    return pages
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow">
        <div className="p-6">
          <div className="animate-pulse space-y-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="flex items-center space-x-4">
                <div className="w-4 h-4 bg-gray-200 rounded-full"></div>
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-gray-200 rounded w-1/4"></div>
                  <div className="h-3 bg-gray-200 rounded w-1/2"></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-medium text-gray-900">
              デバイス一覧 ({totalDevices}件)
            </h3>
            <button
              onClick={onRefresh}
              className="text-sm text-blue-600 hover:text-blue-500"
            >
              更新
            </button>
          </div>
        </div>

        {devices.length === 0 ? (
          <div className="p-6 text-center text-gray-500">
            デバイスが登録されていません
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {devices.map((device) => {
              const statusDisplay = getStatusDisplay(device.status, device.connection_status)
              return (
                <div key={device.id} className="p-6 hover:bg-gray-50">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3">
                        <div className={`w-3 h-3 rounded-full ${statusDisplay.color}`}></div>
                        <div>
                          <h4 className="text-lg font-medium text-gray-900">
                            {device.device_name}
                          </h4>
                          <p className="text-sm text-gray-500">
                            ID: {device.device_id} | タイプ: {getDeviceTypeDisplay(device.device_type)}
                          </p>
                        </div>
                      </div>

                      <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                        <div>
                          <span className="font-medium text-gray-700">状態:</span>
                          <span className={`ml-2 ${statusDisplay.textColor}`}>
                            {statusDisplay.text}
                          </span>
                        </div>
                        <div>
                          <span className="font-medium text-gray-700">場所:</span>
                          <span className="ml-2 text-gray-600">
                            {device.location || '未設定'}
                          </span>
                        </div>
                        <div>
                          <span className="font-medium text-gray-700">最終確認:</span>
                          <span className="ml-2 text-gray-600">
                            {device.last_seen
                              ? format(new Date(device.last_seen), 'MM/dd HH:mm', { locale: ja })
                              : '未確認'
                            }
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3 ml-4">
                      <button
                        onClick={() => {
                          // 編集モーダルを開く（後で実装）
                          console.log('Edit device:', device)
                        }}
                        className="text-sm text-blue-600 hover:text-blue-500"
                      >
                        編集
                      </button>
                      <button
                        onClick={() => {
                          setSelectedDevice(device)
                          setShowDeleteConfirm(true)
                        }}
                        className="text-sm text-red-600 hover:text-red-500"
                      >
                        削除
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* ページネーション */}
        {totalPages > 1 && (
          <div className="px-6 py-4 border-t border-gray-200">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-700">
                {((currentPage - 1) * pageSize) + 1} - {Math.min(currentPage * pageSize, totalDevices)} / {totalDevices}件
              </div>
              <div className="flex space-x-1">
                <button
                  onClick={() => onPageChange(currentPage - 1)}
                  disabled={currentPage <= 1}
                  className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  前へ
                </button>
                {renderPagination()}
                <button
                  onClick={() => onPageChange(currentPage + 1)}
                  disabled={currentPage >= totalPages}
                  className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  次へ
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 削除確認モーダル */}
      {showDeleteConfirm && selectedDevice && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              デバイスの削除
            </h3>
            <p className="text-sm text-gray-600 mb-6">
              「{selectedDevice.device_name}」を削除しますか？<br />
              この操作は取り消せません。
            </p>
            <div className="flex space-x-4 justify-end">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false)
                  setSelectedDevice(null)
                }}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
              >
                キャンセル
              </button>
              <button
                onClick={handleDeleteDevice}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700"
              >
                削除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}