'use client'

import React, { useState } from 'react'
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

interface CreateDeviceModalProps {
  onClose: () => void
  onDeviceCreated: (device: Device) => void
}

export default function CreateDeviceModal({ onClose, onDeviceCreated }: CreateDeviceModalProps) {
  const [formData, setFormData] = useState({
    device_id: '',
    device_name: '',
    device_type: 'raspberry_pi',
    location: ''
  })
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setErrors({})

    try {
      const deviceData = {
        device_id: formData.device_id.trim(),
        device_name: formData.device_name.trim(),
        device_type: formData.device_type,
        location: formData.location.trim() || undefined
      }

      const newDevice = await api.devices.create(deviceData)
      onDeviceCreated(newDevice)

    } catch (error: any) {
      console.error('Failed to create device:', error)
      setErrors({ general: error.message || 'デバイス作成に失敗しました' })
    } finally {
      setLoading(false)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))

    // エラーをクリア
    if (errors[name]) {
      setErrors(prev => {
        const newErrors = { ...prev }
        delete newErrors[name]
        return newErrors
      })
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-medium text-gray-900">
            新しいデバイスを追加
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* 一般エラー */}
          {errors.general && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md text-sm">
              {errors.general}
            </div>
          )}

          {/* デバイスID */}
          <div>
            <label htmlFor="device_id" className="block text-sm font-medium text-gray-700 mb-1">
              デバイスID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              id="device_id"
              name="device_id"
              value={formData.device_id}
              onChange={handleInputChange}
              required
              placeholder="例: lab-device-001"
              className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 text-sm ${
                errors.device_id
                  ? 'border-red-300 focus:ring-red-500 focus:border-red-500'
                  : 'border-gray-300 focus:ring-blue-500 focus:border-blue-500'
              }`}
            />
            <p className="mt-1 text-xs text-gray-500">
              英数字、アンダースコア、ハイフンのみ使用可能
            </p>
            {errors.device_id && (
              <p className="mt-1 text-xs text-red-600">{errors.device_id}</p>
            )}
          </div>

          {/* デバイス名 */}
          <div>
            <label htmlFor="device_name" className="block text-sm font-medium text-gray-700 mb-1">
              デバイス名 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              id="device_name"
              name="device_name"
              value={formData.device_name}
              onChange={handleInputChange}
              required
              placeholder="例: ラボ計測デバイス #1"
              className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 text-sm ${
                errors.device_name
                  ? 'border-red-300 focus:ring-red-500 focus:border-red-500'
                  : 'border-gray-300 focus:ring-blue-500 focus:border-blue-500'
              }`}
            />
            {errors.device_name && (
              <p className="mt-1 text-xs text-red-600">{errors.device_name}</p>
            )}
          </div>

          {/* デバイスタイプ */}
          <div>
            <label htmlFor="device_type" className="block text-sm font-medium text-gray-700 mb-1">
              デバイスタイプ
            </label>
            <select
              id="device_type"
              name="device_type"
              value={formData.device_type}
              onChange={handleInputChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
            >
              <option value="raspberry_pi">Raspberry Pi</option>
              <option value="esp32">ESP32</option>
              <option value="other">その他</option>
            </select>
          </div>

          {/* 設置場所 */}
          <div>
            <label htmlFor="location" className="block text-sm font-medium text-gray-700 mb-1">
              設置場所
            </label>
            <input
              type="text"
              id="location"
              name="location"
              value={formData.location}
              onChange={handleInputChange}
              placeholder="例: 研究室A-101"
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
            />
            <p className="mt-1 text-xs text-gray-500">
              省略可能
            </p>
          </div>

          {/* ボタン */}
          <div className="flex space-x-4 pt-6">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 border border-gray-300 rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500"
            >
              キャンセル
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '作成中...' : 'デバイスを作成'}
            </button>
          </div>
        </form>

        {/* 作成後の手順説明 */}
        <div className="mt-6 p-4 bg-blue-50 rounded-md">
          <h4 className="text-sm font-medium text-blue-900 mb-2">
            デバイス作成後の手順
          </h4>
          <ol className="text-xs text-blue-800 space-y-1 list-decimal list-inside">
            <li>デバイス側でこのデバイスIDを設定</li>
            <li>CSI解析プログラムを起動</li>
            <li>ハートビート送信を開始</li>
            <li>デバイス一覧でオンライン状態を確認</li>
          </ol>
        </div>
      </div>
    </div>
  )
}