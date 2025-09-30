'use client'

import React, { useState, useEffect, useCallback } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { format } from 'date-fns'

interface DataPoint {
  timestamp: string
  value: number
  formatted_time: string
}

interface RealtimeChartProps {
  title: string
  data: DataPoint[]
  dataKey: string
  maxDataPoints?: number
  height?: number
  color?: string
  unit?: string
  yAxisDomain?: [number, number]
}

export default function RealtimeChart({
  title,
  data,
  dataKey,
  maxDataPoints = 50,
  height = 300,
  color = '#3b82f6',
  unit = '',
  yAxisDomain,
}: RealtimeChartProps) {
  const [chartData, setChartData] = useState<DataPoint[]>([])

  // データ更新の処理
  useEffect(() => {
    if (data && data.length > 0) {
      const newData = data.slice(-maxDataPoints).map((point) => ({
        ...point,
        formatted_time: format(new Date(point.timestamp), 'HH:mm:ss'),
      }))
      setChartData(newData)
    }
  }, [data, maxDataPoints])

  // カスタムツールチップ
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-3 shadow-lg rounded-lg border">
          <p className="text-sm font-medium">{`時刻: ${label}`}</p>
          <p className="text-sm" style={{ color: payload[0].color }}>
            {`${title}: ${payload[0].value}${unit}`}
          </p>
        </div>
      )
    }
    return null
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-gray-900">{title}</h3>
        <div className="flex items-center space-x-2">
          <div className="w-3 h-3 rounded-full bg-green-500"></div>
          <span className="text-sm text-gray-500">リアルタイム</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="formatted_time"
            tick={{ fontSize: 12 }}
            tickLine={{ stroke: '#e0e0e0' }}
          />
          <YAxis
            domain={yAxisDomain || ['dataMin - 1', 'dataMax + 1']}
            tick={{ fontSize: 12 }}
            tickLine={{ stroke: '#e0e0e0' }}
            label={{ value: unit, angle: -90, position: 'insideLeft' }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            dot={{ fill: color, strokeWidth: 0, r: 3 }}
            activeDot={{ r: 5, stroke: color, strokeWidth: 2 }}
            name={title}
          />
        </LineChart>
      </ResponsiveContainer>

      {/* データポイント数の表示 */}
      <div className="mt-2 text-xs text-gray-400 text-right">
        データポイント: {chartData.length}/{maxDataPoints}
      </div>
    </div>
  )
}

// 呼吸解析用の特化チャート
export function BreathingRateChart({ deviceId, data }: { deviceId: string; data: any[] }) {
  return (
    <RealtimeChart
      title={`呼吸数 - ${deviceId}`}
      data={data}
      dataKey="breathing_rate"
      color="#10b981"
      unit=" bpm"
      yAxisDomain={[10, 30]}
      maxDataPoints={30}
    />
  )
}

// 信頼度チャート
export function ConfidenceChart({ deviceId, data }: { deviceId: string; data: any[] }) {
  return (
    <RealtimeChart
      title={`信頼度 - ${deviceId}`}
      data={data}
      dataKey="confidence"
      color="#f59e0b"
      unit="%"
      yAxisDomain={[0, 100]}
      maxDataPoints={30}
    />
  )
}

// マルチライン対応のチャート
interface MultiLineChartProps {
  title: string
  data: DataPoint[]
  lines: Array<{
    dataKey: string
    color: string
    name: string
  }>
  height?: number
  maxDataPoints?: number
}

export function MultiLineChart({
  title,
  data,
  lines,
  height = 300,
  maxDataPoints = 50,
}: MultiLineChartProps) {
  const [chartData, setChartData] = useState<DataPoint[]>([])

  useEffect(() => {
    if (data && data.length > 0) {
      const newData = data.slice(-maxDataPoints).map((point) => ({
        ...point,
        formatted_time: format(new Date(point.timestamp), 'HH:mm:ss'),
      }))
      setChartData(newData)
    }
  }, [data, maxDataPoints])

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-gray-900">{title}</h3>
        <div className="flex items-center space-x-2">
          <div className="w-3 h-3 rounded-full bg-green-500"></div>
          <span className="text-sm text-gray-500">リアルタイム</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="formatted_time"
            tick={{ fontSize: 12 }}
            tickLine={{ stroke: '#e0e0e0' }}
          />
          <YAxis tick={{ fontSize: 12 }} tickLine={{ stroke: '#e0e0e0' }} />
          <Tooltip />
          <Legend />
          {lines.map((line) => (
            <Line
              key={line.dataKey}
              type="monotone"
              dataKey={line.dataKey}
              stroke={line.color}
              strokeWidth={2}
              dot={{ fill: line.color, strokeWidth: 0, r: 3 }}
              activeDot={{ r: 5, stroke: line.color, strokeWidth: 2 }}
              name={line.name}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}