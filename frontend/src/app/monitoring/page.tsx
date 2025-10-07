'use client'

import React, { useState, useEffect } from 'react'
import { Activity, Wifi, WifiOff, AlertTriangle } from 'lucide-react'
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

// 簡易Badge コンポーネント
const Badge = ({ children, variant = 'default', className = '' }: {
  children: React.ReactNode
  variant?: 'default' | 'destructive'
  className?: string
}) => (
  <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
    variant === 'destructive'
      ? 'bg-red-100 text-red-800'
      : 'bg-blue-100 text-blue-800'
  } ${className}`}>
    {children}
  </span>
)

// 簡易Card コンポーネント
const Card = ({ children, className = '' }: { children: React.ReactNode, className?: string }) => (
  <div className={`bg-white shadow rounded-lg ${className}`}>
    {children}
  </div>
)

const CardHeader = ({ children }: { children: React.ReactNode }) => (
  <div className="px-6 py-4 border-b border-gray-200">
    {children}
  </div>
)

const CardTitle = ({ children, className = '' }: { children: React.ReactNode, className?: string }) => (
  <h3 className={`text-lg font-medium text-gray-900 ${className}`}>
    {children}
  </h3>
)

const CardContent = ({ children, className = '' }: { children: React.ReactNode, className?: string }) => (
  <div className={`px-6 py-4 ${className}`}>
    {children}
  </div>
)

// 簡易Button コンポーネント
const Button = ({
  children,
  onClick,
  disabled = false,
  variant = 'default',
  size = 'md',
  className = ''
}: {
  children: React.ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'default' | 'outline' | 'destructive'
  size?: 'sm' | 'md'
  className?: string
}) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={`
      inline-flex items-center justify-center rounded-md font-medium transition-colors
      ${size === 'sm' ? 'px-3 py-2 text-sm' : 'px-4 py-2 text-base'}
      ${variant === 'outline'
        ? 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
        : variant === 'destructive'
        ? 'bg-red-600 text-white hover:bg-red-700'
        : 'bg-blue-600 text-white hover:bg-blue-700'
      }
      ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
      ${className}
    `}
  >
    {children}
  </button>
)

// 簡易Select コンポーネント
const Select = ({ value, onValueChange, children }: {
  value: string
  onValueChange: (value: string) => void
  children: React.ReactNode
}) => (
  <div className="relative">
    <select
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
      className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
    >
      {children}
    </select>
  </div>
)

const SelectOption = ({ value, children }: { value: string, children: React.ReactNode }) => (
  <option value={value}>{children}</option>
)

export default function SimpleMonitoringPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [realtimeData, setRealtimeData] = useState<any>(null)

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

  // WebSocket接続（簡易版）
  useEffect(() => {
    if (!selectedDeviceId) return

    const connectWebSocket = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const host = window.location.host.replace(':3000', ':8000')
        const wsUrl = `${protocol}//${host}/api/v2/ws`

        const ws = new WebSocket(wsUrl)

        ws.onopen = () => {
          console.log('WebSocket接続成功')
          setWsStatus('connected')

          // リアルタイム監視チャンネルに購読
          ws.send(JSON.stringify({
            type: 'subscribe',
            channel: `realtime_csi_${selectedDeviceId}`
          }))
        }

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data)
            if (message.type === 'csi_analysis_realtime' && message.device_id === selectedDeviceId) {
              setRealtimeData(message.data)
            }
          } catch (error) {
            console.error('WebSocketメッセージパースエラー:', error)
          }
        }

        ws.onclose = () => {
          console.log('WebSocket接続が閉じられました')
          setWsStatus('disconnected')
        }

        ws.onerror = (error) => {
          console.error('WebSocketエラー:', error)
          setWsStatus('disconnected')
        }

        return ws
      } catch (error) {
        console.error('WebSocket接続エラー:', error)
        setWsStatus('disconnected')
        return null
      }
    }

    const ws = connectWebSocket()

    return () => {
      if (ws) {
        ws.close()
      }
    }
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

      {/* WebSocket状態表示 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Activity className="w-5 h-5" />
            <span>接続状態</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center space-x-4">
            <Badge variant={wsStatus === 'connected' ? 'default' : 'destructive'}>
              {wsStatus === 'connected' ? '接続中' : wsStatus === 'connecting' ? '接続中...' : '切断'}
            </Badge>
            <span className="text-sm text-gray-600">
              WebSocket: {wsStatus}
            </span>
          </div>
        </CardContent>
      </Card>

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
                <SelectOption value="">監視するデバイスを選択してください</SelectOption>
                {devices.map((device) => {
                  const status = getDeviceStatus(device)
                  return (
                    <SelectOption key={device.device_id} value={device.device_id}>
                      {device.device_name || device.device_id} - {status.label}
                    </SelectOption>
                  )
                })}
              </Select>
            </div>

            {selectedDevice && (
              <div className="flex items-center space-x-4">
                <div className="text-sm text-gray-600">
                  <div><strong>場所:</strong> {selectedDevice.location || '未設定'}</div>
                  <div><strong>タイプ:</strong> {selectedDevice.device_type}</div>
                </div>
                <Badge>
                  {getDeviceStatus(selectedDevice).label}
                </Badge>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* リアルタイムデータ表示 */}
      {selectedDeviceId && realtimeData && (
        <Card>
          <CardHeader>
            <CardTitle>リアルタイム呼吸データ - {selectedDeviceId}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="text-center p-4 bg-blue-50 rounded">
                <div className="text-2xl font-bold">{realtimeData.breathing_rate?.toFixed(1) || '0.0'}</div>
                <div className="text-sm text-gray-500">呼吸数（回/分）</div>
              </div>
              <div className="text-center p-4 bg-green-50 rounded">
                <div className="text-xl font-bold">{((realtimeData.breathing_confidence || 0) * 100).toFixed(1)}%</div>
                <div className="text-sm text-gray-500">信頼度</div>
              </div>
              <div className="text-center p-4 bg-yellow-50 rounded">
                <div className="text-xl font-bold">{((realtimeData.signal_quality || 0) * 100).toFixed(1)}%</div>
                <div className="text-sm text-gray-500">信号品質</div>
              </div>
              <div className="text-center p-4 bg-purple-50 rounded">
                <div className="text-xl font-bold">{realtimeData.motion_detected ? 'あり' : 'なし'}</div>
                <div className="text-sm text-gray-500">動作検出</div>
              </div>
            </div>
            <div className="mt-4 text-sm text-gray-500">
              最終更新: {realtimeData.timestamp ? new Date(realtimeData.timestamp).toLocaleString() : '未受信'}
            </div>
          </CardContent>
        </Card>
      )}

      {selectedDeviceId && !realtimeData && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center">
              <Activity className="w-12 h-12 mx-auto mb-4 text-gray-400" />
              <h3 className="text-lg font-medium mb-2">データを待機中...</h3>
              <p className="text-gray-600">
                デバイスからのリアルタイムデータを待機しています
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {!selectedDeviceId && (
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

      {/* デバイス統計 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="text-center">
              <div className="text-2xl font-bold">{devices.length}</div>
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