'use client'

import React from 'react'
import MainLayout from '@/components/layout/MainLayout'
import { ProtectedPage } from '@/components/auth/AuthGuard'
import RealtimeDashboard from '@/components/realtime/RealtimeDashboard'

export default function RealtimePage() {
  return (
    <ProtectedPage>
      <MainLayout>
        <div className="space-y-6">
          {/* ページヘッダー */}
          <div className="md:flex md:items-center md:justify-between">
            <div className="flex-1 min-w-0">
              <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                リアルタイム監視
              </h2>
              <p className="mt-1 text-sm text-gray-500">
                WebSocket接続によるリアルタイムデータ監視とグラフ表示
              </p>
            </div>
          </div>

          {/* リアルタイムダッシュボード */}
          <RealtimeDashboard />
        </div>
      </MainLayout>
    </ProtectedPage>
  )
}