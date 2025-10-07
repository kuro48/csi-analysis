'use client'

import React, { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
// import { Alert, AlertDescription } from '@/components/ui/alert'
import { Activity, Wifi, WifiOff, AlertTriangle, CheckCircle } from 'lucide-react'
import RealtimeBreathingMonitor from '@/components/visualization/RealtimeBreathingMonitor'
import { apiClient } from '@/services/api'

interface Device {
  id: string
  device_id: string
  device_name: string
  device_type: string
  location: string
  is_active: boolean
  last_seen: string | null
}

export default function MonitoringPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // デバイス一覧を取得
  useEffect(() => {
    const fetchDevices = async () => {
      try {
        setLoading(true)
        const response = await apiClient.get('/api/v2/devices/')
        setDevices(response.data.devices || [])

        // 最初のアクティブなデバイスを選択
        const activeDevices = response.data.devices?.filter((d: Device) => d.is_active) || []
        if (activeDevices.length > 0 && !selectedDeviceId) {
          setSelectedDeviceId(activeDevices[0].device_id)
        }
      } catch (err) {
        console.error('デバイス一覧取得エラー:', err)
        setError('デバイス一覧の取得に失敗しました')
      } finally {
        setLoading(false)
      }
    }

    fetchDevices()
  }, [selectedDeviceId])

  const getDeviceStatus = (device: Device) => {
    if (!device.is_active) {
      return { status: 'inactive', label: '非アクティブ', color: 'bg-gray-500', icon: WifiOff }
    }

    if (!device.last_seen) {
      return { status: 'unknown', label: '不明', color: 'bg-gray-400', icon: WifiOff }
    }

    const lastSeen = new Date(device.last_seen)
    const now = new Date()
    const diffMinutes = (now.getTime() - lastSeen.getTime()) / (1000 * 60)

    if (diffMinutes < 5) {
      return { status: 'online', label: 'オンライン', color: 'bg-green-500', icon: Wifi }
    } else if (diffMinutes < 30) {
      return { status: 'idle', label: 'アイドル', color: 'bg-yellow-500', icon: AlertTriangle }
    } else {
      return { status: 'offline', label: 'オフライン', color: 'bg-red-500', icon: WifiOff }
    }
  }

  const selectedDevice = devices.find(d => d.device_id === selectedDeviceId)

  if (loading) {
    return (
      <div className="container mx-auto py-8">
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <Activity className="w-8 h-8 animate-spin mx-auto mb-4" />
            <p>デバイス情報を読み込み中...</p>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="container mx-auto py-8">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          <div className="flex items-center">
            <AlertTriangle className="h-4 w-4 mr-2" />
            <span>{error}</span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto py-8 space-y-6">
      {/* ヘッダー */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">リアルタイム監視</h1>
          <p className="text-gray-600 mt-2">
            CSIデバイスからのリアルタイム呼吸監視データを表示します
          </p>
        </div>
      </div>

      {/* デバイス選択 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Activity className="w-5 h-5" />
            <span>監視デバイス選択</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center space-x-4">
            <div className="flex-1">
              <Select value={selectedDeviceId} onValueChange={setSelectedDeviceId}>
                <SelectTrigger>
                  <SelectValue placeholder="監視するデバイスを選択してください" />
                </SelectTrigger>
                <SelectContent>
                  {devices.map((device) => {
                    const status = getDeviceStatus(device)
                    const StatusIcon = status.icon
                    return (
                      <SelectItem key={device.device_id} value={device.device_id}>
                        <div className="flex items-center space-x-2">
                          <StatusIcon className="w-4 h-4" />
                          <span>{device.device_name || device.device_id}</span>
                          <Badge className={status.color}>
                            {status.label}
                          </Badge>
                        </div>
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>

            {selectedDevice && (
              <div className="flex items-center space-x-4">
                <div className="text-sm text-gray-600">
                  <div><strong>場所:</strong> {selectedDevice.location || '未設定'}</div>
                  <div><strong>タイプ:</strong> {selectedDevice.device_type}</div>
                </div>
                <Badge className={getDeviceStatus(selectedDevice).color}>
                  {getDeviceStatus(selectedDevice).label}
                </Badge>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 監視コンテンツ */}
      {selectedDeviceId ? (
        <Tabs defaultValue="realtime" className="space-y-4">
          <TabsList>
            <TabsTrigger value="realtime">リアルタイム監視</TabsTrigger>
            <TabsTrigger value="history">履歴データ</TabsTrigger>
            <TabsTrigger value="settings">設定</TabsTrigger>
          </TabsList>

          <TabsContent value="realtime">
            <RealtimeBreathingMonitor
              deviceId={selectedDeviceId}
              autoStart={true}
              maxDataPoints={200}
            />
          </TabsContent>

          <TabsContent value="history">
            <Card>
              <CardHeader>
                <CardTitle>履歴データ</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center py-8 text-gray-500">
                  履歴データ表示機能は実装中です
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="settings">
            <Card>
              <CardHeader>
                <CardTitle>監視設定</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-medium mb-2">アラート設定</h3>
                    <div className="text-center py-4 text-gray-500">
                      アラート設定機能は実装中です
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      ) : (
        <Card>
          <CardContent className="py-12">
            <div className="text-center">
              <Activity className="w-12 h-12 mx-auto mb-4 text-gray-400" />
              <h3 className="text-lg font-medium mb-2">デバイスを選択してください</h3>
              <p className="text-gray-600">
                監視を開始するにはアクティブなデバイスを選択してください
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* デバイス情報サマリー */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="text-center">
              <div className="text-2xl font-bold">
                {devices.length}
              </div>
              <div className="text-sm text-gray-500">総デバイス数</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {devices.filter(d => getDeviceStatus(d).status === 'online').length}
              </div>
              <div className="text-sm text-gray-500">オンライン</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-yellow-600">
                {devices.filter(d => getDeviceStatus(d).status === 'idle').length}
              </div>
              <div className="text-sm text-gray-500">アイドル</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">
                {devices.filter(d => getDeviceStatus(d).status === 'offline').length}
              </div>
              <div className="text-sm text-gray-500">オフライン</div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}