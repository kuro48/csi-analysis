'use client'

import React from 'react'
import Link from 'next/link'
import MainLayout from '@/components/layout/MainLayout'
import { ProtectedPage } from '@/components/auth/AuthGuard'
import { useRealTimeData } from '@/hooks/useRealTimeData'

export default function Dashboard() {
  const { data, connectionStatus } = useRealTimeData()

  // リアルタイムデータを基にした統計
  const deviceCount = Object.keys(data.deviceStatuses).length
  const onlineDevices = Object.values(data.deviceStatuses).filter(
    device => device.status === 'online'
  ).length
  const analysisCount = Object.keys(data.breathingAnalyses).length
  const notificationCount = data.systemNotifications.length

  const stats = [
    { name: '接続デバイス', value: deviceCount.toString(), change: connectionStatus === 'Open' ? '接続中' : '切断', icon: '📱' },
    { name: '現在監視中', value: onlineDevices.toString(), change: `${deviceCount}台中`, icon: '👁️' },
    { name: '解析データ', value: analysisCount.toString(), change: 'リアルタイム', icon: '📊' },
    { name: '通知', value: notificationCount.toString(), change: '最新', icon: '🚨' },
  ]

  const recentActivity = [
    { device: 'Lab Device #1', action: '呼吸解析完了', time: '2分前', status: 'success' },
    { device: 'Lab Device #2', action: 'データアップロード', time: '5分前', status: 'info' },
    { device: 'Lab Device #3', action: '異常値検知', time: '10分前', status: 'warning' },
    { device: 'Lab Device #1', action: 'セッション開始', time: '15分前', status: 'info' },
  ]

  return (
    <ProtectedPage>
      <MainLayout>
      <div className="space-y-6">
        {/* ページヘッダー */}
        <div className="md:flex md:items-center md:justify-between">
          <div className="flex-1 min-w-0">
            <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
              ダッシュボード
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              システム全体の状況とリアルタイム情報を確認できます
            </p>
          </div>
          <div className="mt-4 flex space-x-4 md:mt-0 md:ml-4">
            <Link
              href="/dashboard/realtime"
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium"
            >
              リアルタイム監視
            </Link>
            <button className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium">
              レポート生成
            </button>
          </div>
        </div>

        {/* 統計カード */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {stats.map((stat) => (
            <div key={stat.name} className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">{stat.name}</p>
                  <p className="text-3xl font-semibold text-gray-900">{stat.value}</p>
                  <p className="text-sm text-gray-500">{stat.change} 前回比</p>
                </div>
                <div className="text-3xl">{stat.icon}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* リアルタイム監視 */}
          <div className="bg-white rounded-lg shadow">
            <div className="p-6 border-b border-gray-200">
              <h3 className="text-lg font-medium text-gray-900">リアルタイム監視</h3>
            </div>
            <div className="p-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-green-50 rounded-lg">
                  <div className="flex items-center space-x-3">
                    <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                    <span className="font-medium">Lab Device #1</span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium">18.2 回/分</p>
                    <p className="text-xs text-gray-500">信頼度: 95%</p>
                  </div>
                </div>
                <div className="flex items-center justify-between p-4 bg-green-50 rounded-lg">
                  <div className="flex items-center space-x-3">
                    <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                    <span className="font-medium">Lab Device #2</span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium">16.8 回/分</p>
                    <p className="text-xs text-gray-500">信頼度: 92%</p>
                  </div>
                </div>
                <div className="flex items-center justify-between p-4 bg-yellow-50 rounded-lg">
                  <div className="flex items-center space-x-3">
                    <div className="w-3 h-3 bg-yellow-500 rounded-full"></div>
                    <span className="font-medium">Lab Device #3</span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium">25.1 回/分</p>
                    <p className="text-xs text-gray-500">信頼度: 78%</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 最近のアクティビティ */}
          <div className="bg-white rounded-lg shadow">
            <div className="p-6 border-b border-gray-200">
              <h3 className="text-lg font-medium text-gray-900">最近のアクティビティ</h3>
            </div>
            <div className="p-6">
              <div className="space-y-4">
                {recentActivity.map((activity, index) => (
                  <div key={index} className="flex items-center space-x-4">
                    <div className={`w-2 h-2 rounded-full ${
                      activity.status === 'success' ? 'bg-green-500' :
                      activity.status === 'warning' ? 'bg-yellow-500' : 'bg-blue-500'
                    }`}></div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">
                        {activity.device}
                      </p>
                      <p className="text-sm text-gray-500">{activity.action}</p>
                    </div>
                    <div className="text-xs text-gray-400">{activity.time}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* システム状態 */}
        <div className="bg-white rounded-lg shadow">
          <div className="p-6 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900">システム状態</h3>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center">
                <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <div className="w-8 h-8 bg-green-500 rounded-full"></div>
                </div>
                <h4 className="font-medium">データベース</h4>
                <p className="text-sm text-gray-500">正常稼働中</p>
              </div>
              <div className="text-center">
                <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <div className="w-8 h-8 bg-green-500 rounded-full"></div>
                </div>
                <h4 className="font-medium">API サーバー</h4>
                <p className="text-sm text-gray-500">正常稼働中</p>
              </div>
              <div className="text-center">
                <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-2">
                  <div className="w-8 h-8 bg-green-500 rounded-full"></div>
                </div>
                <h4 className="font-medium">IPFS ノード</h4>
                <p className="text-sm text-gray-500">正常稼働中</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      </MainLayout>
    </ProtectedPage>
  )
}