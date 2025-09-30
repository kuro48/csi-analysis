/**
 * フォーマット関連のユーティリティ関数
 */

// ファイルサイズを人間が読みやすい形式に変換
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'

  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const size = bytes / Math.pow(1024, i)

  return `${size.toFixed(i === 0 ? 0 : 1)} ${sizes[i]}`
}

// 数値をカンマ区切りで表示
export function formatNumber(num: number): string {
  return num.toLocaleString('ja-JP')
}

// パーセンテージ表示
export function formatPercentage(value: number, decimals: number = 1): string {
  return `${(value * 100).toFixed(decimals)}%`
}

// 呼吸率を表示形式に変換
export function formatBreathingRate(rate: number): string {
  return `${rate.toFixed(1)} 回/分`
}

// 信頼度スコアを表示形式に変換
export function formatConfidenceScore(score: number): string {
  return `${(score * 100).toFixed(0)}%`
}

// デバイスIDを表示用に短縮
export function formatDeviceId(deviceId: string, maxLength: number = 12): string {
  if (deviceId.length <= maxLength) return deviceId
  return `${deviceId.substring(0, maxLength)}...`
}

// ステータスを日本語に変換
export function formatStatus(status: string): string {
  const statusMap: Record<string, string> = {
    active: 'アクティブ',
    inactive: '非アクティブ',
    online: 'オンライン',
    offline: 'オフライン',
    processing: '処理中',
    completed: '完了',
    error: 'エラー',
    pending: '待機中',
    success: '成功',
    failed: '失敗',
    warning: '警告',
    info: '情報',
    received: '受信済み',
    processed: '処理済み',
    stopped: '停止',
  }

  return statusMap[status] || status
}

// アラートタイプを日本語に変換
export function formatAlertType(type: string): string {
  const typeMap: Record<string, string> = {
    breathing_anomaly: '呼吸異常',
    device_offline: 'デバイスオフライン',
    high_breathing_rate: '高呼吸率',
    low_breathing_rate: '低呼吸率',
    connection_lost: '接続断',
    system_error: 'システムエラー',
    data_quality_low: 'データ品質低下',
  }

  return typeMap[type] || type
}

// 重要度を日本語に変換
export function formatSeverity(severity: string): string {
  const severityMap: Record<string, string> = {
    low: '低',
    medium: '中',
    high: '高',
    critical: '緊急',
  }

  return severityMap[severity] || severity
}

// 重要度に応じた色クラスを取得
export function getSeverityColor(severity: string): string {
  const colorMap: Record<string, string> = {
    low: 'text-green-600 bg-green-100',
    medium: 'text-yellow-600 bg-yellow-100',
    high: 'text-orange-600 bg-orange-100',
    critical: 'text-red-600 bg-red-100',
  }

  return colorMap[severity] || 'text-gray-600 bg-gray-100'
}

// ステータスに応じた色クラスを取得
export function getStatusColor(status: string): string {
  const colorMap: Record<string, string> = {
    active: 'text-green-600 bg-green-100',
    online: 'text-green-600 bg-green-100',
    success: 'text-green-600 bg-green-100',
    completed: 'text-green-600 bg-green-100',
    processing: 'text-blue-600 bg-blue-100',
    pending: 'text-yellow-600 bg-yellow-100',
    warning: 'text-yellow-600 bg-yellow-100',
    inactive: 'text-gray-600 bg-gray-100',
    offline: 'text-gray-600 bg-gray-100',
    error: 'text-red-600 bg-red-100',
    failed: 'text-red-600 bg-red-100',
  }

  return colorMap[status] || 'text-gray-600 bg-gray-100'
}