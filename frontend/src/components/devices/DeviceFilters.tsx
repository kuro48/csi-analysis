'use client'

import React, { useState } from 'react'

interface DeviceFilters {
  status: string
  device_type: string
  location: string
  search: string
  is_active?: boolean
}

interface DeviceFiltersProps {
  filters: DeviceFilters
  onFiltersChange: (filters: DeviceFilters) => void
  statistics: {
    total_devices: number
    online_devices: number
    offline_devices: number
    error_devices: number
    by_type: Record<string, number>
    by_location: Record<string, number>
  }
}

export default function DeviceFilters({ filters, onFiltersChange, statistics }: DeviceFiltersProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const handleFilterChange = (key: keyof DeviceFilters, value: string | boolean | undefined) => {
    const newFilters = {
      ...filters,
      [key]: value
    }
    onFiltersChange(newFilters)
  }

  const clearFilters = () => {
    onFiltersChange({
      status: 'all',
      device_type: 'all',
      location: '',
      search: '',
      is_active: undefined
    })
  }

  const hasActiveFilters =
    filters.status !== 'all' ||
    filters.device_type !== 'all' ||
    filters.location !== '' ||
    filters.search !== '' ||
    filters.is_active !== undefined

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">フィルター・検索</h3>
          <div className="flex items-center space-x-4">
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                フィルターをクリア
              </button>
            )}
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-sm text-blue-600 hover:text-blue-500"
            >
              {isExpanded ? '折りたたむ' : '詳細フィルター'}
            </button>
          </div>
        </div>

        {/* 基本フィルター（常に表示） */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* 検索 */}
          <div>
            <label htmlFor="search" className="block text-sm font-medium text-gray-700 mb-1">
              検索
            </label>
            <input
              id="search"
              type="text"
              value={filters.search}
              onChange={(e) => handleFilterChange('search', e.target.value)}
              placeholder="デバイス名、ID、場所で検索"
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
            />
          </div>

          {/* 状態フィルター */}
          <div>
            <label htmlFor="status" className="block text-sm font-medium text-gray-700 mb-1">
              状態
            </label>
            <select
              id="status"
              value={filters.status}
              onChange={(e) => handleFilterChange('status', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
            >
              <option value="all">すべて ({statistics.total_devices})</option>
              <option value="online">オンライン ({statistics.online_devices})</option>
              <option value="offline">オフライン ({statistics.offline_devices})</option>
              <option value="error">エラー ({statistics.error_devices})</option>
            </select>
          </div>

          {/* デバイスタイプフィルター */}
          <div>
            <label htmlFor="device_type" className="block text-sm font-medium text-gray-700 mb-1">
              タイプ
            </label>
            <select
              id="device_type"
              value={filters.device_type}
              onChange={(e) => handleFilterChange('device_type', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
            >
              <option value="all">すべて</option>
              {Object.entries(statistics.by_type).map(([type, count]) => (
                <option key={type} value={type}>
                  {type === 'raspberry_pi' ? 'Raspberry Pi' :
                   type === 'esp32' ? 'ESP32' : type} ({count})
                </option>
              ))}
            </select>
          </div>

          {/* 場所フィルター */}
          <div>
            <label htmlFor="location" className="block text-sm font-medium text-gray-700 mb-1">
              場所
            </label>
            <select
              id="location"
              value={filters.location}
              onChange={(e) => handleFilterChange('location', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
            >
              <option value="">すべて</option>
              {Object.entries(statistics.by_location).map(([location, count]) => (
                <option key={location} value={location}>
                  {location === '未設定' ? '場所未設定' : location} ({count})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 詳細フィルター（展開時のみ表示） */}
        {isExpanded && (
          <div className="mt-6 pt-6 border-t border-gray-200">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* アクティブ状態 */}
              <div>
                <label htmlFor="is_active" className="block text-sm font-medium text-gray-700 mb-1">
                  アクティブ状態
                </label>
                <select
                  id="is_active"
                  value={filters.is_active === undefined ? '' : filters.is_active.toString()}
                  onChange={(e) => {
                    const value = e.target.value === '' ? undefined : e.target.value === 'true'
                    handleFilterChange('is_active', value)
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                >
                  <option value="">すべて</option>
                  <option value="true">アクティブ</option>
                  <option value="false">非アクティブ</option>
                </select>
              </div>

              {/* 追加のフィルター用スペース */}
              <div></div>
              <div></div>
            </div>

            {/* クイックフィルター */}
            <div className="mt-6">
              <label className="block text-sm font-medium text-gray-700 mb-3">
                クイックフィルター
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => handleFilterChange('status', 'online')}
                  className={`px-3 py-1 text-sm rounded-full border ${
                    filters.status === 'online'
                      ? 'bg-green-100 text-green-800 border-green-300'
                      : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  オンラインのみ
                </button>
                <button
                  onClick={() => handleFilterChange('status', 'offline')}
                  className={`px-3 py-1 text-sm rounded-full border ${
                    filters.status === 'offline'
                      ? 'bg-gray-100 text-gray-800 border-gray-300'
                      : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  オフラインのみ
                </button>
                <button
                  onClick={() => handleFilterChange('device_type', 'raspberry_pi')}
                  className={`px-3 py-1 text-sm rounded-full border ${
                    filters.device_type === 'raspberry_pi'
                      ? 'bg-blue-100 text-blue-800 border-blue-300'
                      : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  Raspberry Pi のみ
                </button>
                <button
                  onClick={() => handleFilterChange('is_active', true)}
                  className={`px-3 py-1 text-sm rounded-full border ${
                    filters.is_active === true
                      ? 'bg-yellow-100 text-yellow-800 border-yellow-300'
                      : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  アクティブのみ
                </button>
              </div>
            </div>
          </div>
        )}

        {/* アクティブなフィルターの表示 */}
        {hasActiveFilters && (
          <div className="mt-4 pt-4 border-t border-gray-200">
            <div className="flex items-center space-x-2">
              <span className="text-sm font-medium text-gray-700">適用中:</span>
              <div className="flex flex-wrap gap-2">
                {filters.status !== 'all' && (
                  <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">
                    状態: {filters.status}
                  </span>
                )}
                {filters.device_type !== 'all' && (
                  <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">
                    タイプ: {filters.device_type}
                  </span>
                )}
                {filters.location && (
                  <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">
                    場所: {filters.location}
                  </span>
                )}
                {filters.search && (
                  <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">
                    検索: {filters.search}
                  </span>
                )}
                {filters.is_active !== undefined && (
                  <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">
                    {filters.is_active ? 'アクティブ' : '非アクティブ'}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}