'use client'

import React, { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  AreaChart
} from 'recharts'
import { format } from 'date-fns'
import { ja } from 'date-fns/locale'

interface BreathingDataPoint {
  timestamp: string
  value: number | null
}

interface BreathingAnalysisChartProps {
  breathingData: BreathingDataPoint[]
  confidenceData?: BreathingDataPoint[]
  title?: string
  height?: number
  showConfidence?: boolean
}

const BreathingAnalysisChart = React.memo(function BreathingAnalysisChart({
  breathingData,
  confidenceData = [],
  title = "呼吸解析結果",
  height = 300,
  showConfidence = true
}: BreathingAnalysisChartProps) {

  // データポイントを結合・整理（メモ化で最適化）
  const chartData = useMemo(() => {
    return breathingData.map((breathingPoint, index) => {
      const confidencePoint = confidenceData[index]

      return {
        timestamp: breathingPoint.timestamp,
        breathingRate: breathingPoint.value,
        confidence: confidencePoint?.value || null,
        formattedTime: format(new Date(breathingPoint.timestamp), 'HH:mm', { locale: ja })
      }
    }).filter(point => point.breathingRate !== null)
  }, [breathingData, confidenceData])

  // カスタムツールチップ
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="text-sm font-medium text-gray-900">
            {format(new Date(data.timestamp), 'MM/dd HH:mm:ss', { locale: ja })}
          </p>
          <div className="mt-2 space-y-1">
            <p className="text-sm text-blue-600">
              <span className="inline-block w-3 h-3 bg-blue-500 rounded-full mr-2"></span>
              呼吸数: {data.breathingRate?.toFixed(1) || 'N/A'} 回/分
            </p>
            {showConfidence && data.confidence !== null && (
              <p className="text-sm text-green-600">
                <span className="inline-block w-3 h-3 bg-green-500 rounded-full mr-2"></span>
                信頼度: {(data.confidence * 100).toFixed(1)}%
              </p>
            )}
          </div>
        </div>
      )
    }
    return null
  }

  const getBreathingRateColor = (rate: number) => {
    if (rate < 8 || rate > 40) return '#EF4444' // 異常値：赤
    if (rate < 12 || rate > 25) return '#F59E0B' // 注意：オレンジ
    return '#3B82F6' // 正常：青
  }

  if (chartData.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">{title}</h3>
        <div className="flex items-center justify-center h-64 text-gray-500">
          <div className="text-center">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <p className="mt-2 text-sm">解析データがありません</p>
          </div>
        </div>
      </div>
    )
  }

  // 統計情報計算（メモ化で最適化）
  const statistics = useMemo(() => {
    const validRates = chartData.filter(d => d.breathingRate !== null).map(d => d.breathingRate!) // non-null assertion
    const avgRate = validRates.length > 0 ? validRates.reduce((sum, rate) => sum + rate, 0) / validRates.length : 0
    const minRate = validRates.length > 0 ? Math.min(...validRates) : 0
    const maxRate = validRates.length > 0 ? Math.max(...validRates) : 0

    return { avgRate, minRate, maxRate }
  }, [chartData])

  const { avgRate, minRate, maxRate } = statistics

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">{title}</h3>
          <div className="flex items-center space-x-4 text-sm">
            <div className="flex items-center">
              <div className="w-3 h-3 bg-blue-500 rounded-full mr-2"></div>
              <span className="text-gray-600">呼吸数</span>
            </div>
            {showConfidence && (
              <div className="flex items-center">
                <div className="w-3 h-3 bg-green-500 rounded-full mr-2"></div>
                <span className="text-gray-600">信頼度</span>
              </div>
            )}
          </div>
        </div>

        {/* 統計サマリー */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="text-center p-3 bg-gray-50 rounded-lg">
            <div className="text-2xl font-semibold text-gray-900">
              {avgRate.toFixed(1)}
            </div>
            <div className="text-sm text-gray-600">平均呼吸数</div>
            <div className="text-xs text-gray-500">回/分</div>
          </div>
          <div className="text-center p-3 bg-gray-50 rounded-lg">
            <div className="text-2xl font-semibold text-red-600">
              {maxRate.toFixed(1)}
            </div>
            <div className="text-sm text-gray-600">最大</div>
            <div className="text-xs text-gray-500">回/分</div>
          </div>
          <div className="text-center p-3 bg-gray-50 rounded-lg">
            <div className="text-2xl font-semibold text-blue-600">
              {minRate.toFixed(1)}
            </div>
            <div className="text-sm text-gray-600">最小</div>
            <div className="text-xs text-gray-500">回/分</div>
          </div>
        </div>

        {/* チャート */}
        <div style={{ height: `${height}px` }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="formattedTime"
                tick={{ fontSize: 12 }}
                tickLine={{ stroke: '#d1d5db' }}
              />
              <YAxis
                yAxisId="breathing"
                orientation="left"
                domain={[0, 50]}
                tick={{ fontSize: 12 }}
                tickLine={{ stroke: '#d1d5db' }}
                label={{ value: '呼吸数 (回/分)', angle: -90, position: 'insideLeft' }}
              />
              {showConfidence && (
                <YAxis
                  yAxisId="confidence"
                  orientation="right"
                  domain={[0, 1]}
                  tick={{ fontSize: 12 }}
                  tickLine={{ stroke: '#d1d5db' }}
                  label={{ value: '信頼度', angle: 90, position: 'insideRight' }}
                />
              )}
              <Tooltip content={<CustomTooltip />} />
              <Legend />

              {/* 正常範囲の背景 */}
              <Area
                yAxisId="breathing"
                type="monotone"
                dataKey={() => 25}
                fill="#dbeafe"
                fillOpacity={0.3}
                stroke="none"
                name="正常範囲上限"
              />
              <Area
                yAxisId="breathing"
                type="monotone"
                dataKey={() => 12}
                fill="#ffffff"
                fillOpacity={1}
                stroke="none"
                name="正常範囲下限"
              />

              {/* 呼吸数ライン */}
              <Line
                yAxisId="breathing"
                type="monotone"
                dataKey="breathingRate"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={{ fill: '#3b82f6', strokeWidth: 2, r: 3 }}
                activeDot={{ r: 5 }}
                name="呼吸数"
              />

              {/* 信頼度ライン */}
              {showConfidence && (
                <Line
                  yAxisId="confidence"
                  type="monotone"
                  dataKey="confidence"
                  stroke="#10b981"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={{ fill: '#10b981', strokeWidth: 2, r: 2 }}
                  name="信頼度"
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* 異常値警告 */}
        {(minRate < 8 || maxRate > 40) && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
            <div className="flex items-center">
              <svg className="w-5 h-5 text-red-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <span className="text-sm text-red-800 font-medium">
                異常な呼吸数が検出されました
              </span>
            </div>
            <p className="text-sm text-red-700 mt-1">
              正常範囲（12-25回/分）を外れた値があります。詳細な診断を推奨します。
            </p>
          </div>
        )}
      </div>
    </div>
  )
})

export default BreathingAnalysisChart