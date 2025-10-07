'use client'

import React, { useState, useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Brush
} from 'recharts'

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

interface CSIChartProps {
  data: CSIVisualizationData
  className?: string
}

const CSIChart: React.FC<CSIChartProps> = ({ data, className = '' }) => {
  const [selectedMetric, setSelectedMetric] = useState<'amplitude' | 'phase'>('amplitude')
  const [selectedSubcarriers, setSelectedSubcarriers] = useState<string[]>([])

  // チャート用データの変換
  const chartData = useMemo(() => {
    if (!data.subcarrier_data) return []

    const subcarrierKeys = Object.keys(data.subcarrier_data)
    if (subcarrierKeys.length === 0) return []

    // 選択されたサブキャリア（デフォルトで最初の5つ）
    const activeSubcarriers = selectedSubcarriers.length > 0
      ? selectedSubcarriers
      : subcarrierKeys.slice(0, Math.min(5, subcarrierKeys.length))

    // 最初のサブキャリアのタイムスタンプを基準にする
    const firstSubcarrier = data.subcarrier_data[activeSubcarriers[0]]
    if (!firstSubcarrier) return []

    const timestamps = firstSubcarrier.timestamps

    return timestamps.map((timestamp, index) => {
      const dataPoint: any = {
        timestamp: timestamp,
        time_label: new Date(timestamp * 1000).toLocaleTimeString()
      }

      activeSubcarriers.forEach(scKey => {
        const scData = data.subcarrier_data[scKey]
        if (scData && index < scData[selectedMetric === 'amplitude' ? 'amplitudes' : 'phases'].length) {
          const value = selectedMetric === 'amplitude'
            ? scData.amplitudes[index]
            : scData.phases[index]
          dataPoint[scKey] = value
        }
      })

      return dataPoint
    })
  }, [data, selectedMetric, selectedSubcarriers])

  // サブキャリア選択のオプション
  const subcarrierOptions = useMemo(() => {
    return Object.keys(data.subcarrier_data || {}).map(key => ({
      value: key,
      label: key.replace('subcarrier_', 'SC ')
    }))
  }, [data])

  // アクティブなサブキャリアの色
  const colors = [
    '#2563eb', '#dc2626', '#16a34a', '#ca8a04', '#9333ea',
    '#c2410c', '#0891b2', '#be123c', '#4338f3', '#059669'
  ]

  const activeSubcarriers = selectedSubcarriers.length > 0
    ? selectedSubcarriers
    : Object.keys(data.subcarrier_data || {}).slice(0, 5)

  const handleSubcarrierToggle = (scKey: string) => {
    setSelectedSubcarriers(prev => {
      if (prev.includes(scKey)) {
        return prev.filter(key => key !== scKey)
      } else {
        return [...prev, scKey].slice(0, 10) // 最大10個まで
      }
    })
  }

  const formatTooltipValue = (value: number, name: string) => {
    const unit = selectedMetric === 'amplitude' ? '' : ' rad'
    return [value?.toFixed(4) + unit, name.replace('subcarrier_', 'SC ')]
  }

  return (
    <div className={`bg-white rounded-lg shadow-sm border p-6 ${className}`}>
      {/* ヘッダー */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-medium text-gray-900">
            CSI {selectedMetric === 'amplitude' ? '振幅' : '位相'} グラフ
          </h3>
          <p className="text-sm text-gray-500">
            デバイス: {data.metadata.device_id} |
            サブキャリア: {data.metadata.displayed_subcarriers}/{data.metadata.total_subcarriers}
          </p>
        </div>

        {/* メトリック選択 */}
        <div className="flex space-x-2">
          <button
            onClick={() => setSelectedMetric('amplitude')}
            className={`px-3 py-2 text-sm font-medium rounded-md ${
              selectedMetric === 'amplitude'
                ? 'bg-blue-100 text-blue-700'
                : 'text-gray-700 hover:text-gray-900'
            }`}
          >
            振幅
          </button>
          <button
            onClick={() => setSelectedMetric('phase')}
            className={`px-3 py-2 text-sm font-medium rounded-md ${
              selectedMetric === 'phase'
                ? 'bg-blue-100 text-blue-700'
                : 'text-gray-700 hover:text-gray-900'
            }`}
          >
            位相
          </button>
        </div>
      </div>

      {/* サブキャリア選択 */}
      <div className="mb-4">
        <div className="text-sm font-medium text-gray-700 mb-2">表示サブキャリア (最大10個)</div>
        <div className="flex flex-wrap gap-2">
          {subcarrierOptions.slice(0, 20).map((option, index) => (
            <button
              key={option.value}
              onClick={() => handleSubcarrierToggle(option.value)}
              className={`px-2 py-1 text-xs font-medium rounded ${
                activeSubcarriers.includes(option.value)
                  ? 'bg-blue-100 text-blue-700 border border-blue-300'
                  : 'bg-gray-100 text-gray-700 border border-gray-300 hover:bg-gray-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {/* チャート */}
      <div className="h-96">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="time_label"
              tick={{ fontSize: 12 }}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 12 }}
              label={{
                value: selectedMetric === 'amplitude' ? '振幅' : '位相 (rad)',
                angle: -90,
                position: 'insideLeft'
              }}
            />
            <Tooltip
              formatter={formatTooltipValue}
              labelFormatter={(label) => `時刻: ${label}`}
            />
            <Legend />

            {activeSubcarriers.map((scKey, index) => (
              <Line
                key={scKey}
                type="monotone"
                dataKey={scKey}
                stroke={colors[index % colors.length]}
                strokeWidth={1.5}
                dot={false}
                name={scKey.replace('subcarrier_', 'SC ')}
              />
            ))}

            <Brush dataKey="time_label" height={30} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* 統計情報 */}
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div className="bg-gray-50 p-3 rounded">
          <div className="font-medium text-gray-700">サンプル数</div>
          <div className="text-xl font-bold text-gray-900">
            {data.summary.n_samples?.toLocaleString() || 0}
          </div>
        </div>
        <div className="bg-gray-50 p-3 rounded">
          <div className="font-medium text-gray-700">サブキャリア数</div>
          <div className="text-xl font-bold text-gray-900">
            {data.summary.n_subcarriers || 0}
          </div>
        </div>
        <div className="bg-gray-50 p-3 rounded">
          <div className="font-medium text-gray-700">時間範囲</div>
          <div className="text-sm font-medium text-gray-900">
            {data.summary.time_range ?
              `${((data.summary.time_range.end - data.summary.time_range.start) / 60).toFixed(1)}分`
              : '不明'
            }
          </div>
        </div>
        <div className="bg-gray-50 p-3 rounded">
          <div className="font-medium text-gray-700">表示中</div>
          <div className="text-sm font-medium text-gray-900">
            {activeSubcarriers.length} / {data.metadata.total_subcarriers}
          </div>
        </div>
      </div>
    </div>
  )
}

export default CSIChart