'use client'

import React, { useState, useCallback, useMemo } from 'react'
import { apiClient } from '@/services/api'

interface CSIUploadModalProps {
  deviceId?: string
  onClose: () => void
  onUploadComplete: (uploadedData: any) => void
}

const CSIUploadModal = React.memo(function CSIUploadModal({ deviceId: initialDeviceId, onClose, onUploadComplete }: CSIUploadModalProps) {
  const [deviceId, setDeviceId] = useState(initialDeviceId || '')
  const [file, setFile] = useState<File | null>(null)
  const [sessionId, setSessionId] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState('')

  // ファイル検証設定（メモ化）
  const fileValidation = useMemo(() => ({
    allowedTypes: ['.pcap', '.csv', '.json'],
    maxSize: 100 * 1024 * 1024, // 100MB
    errorMessages: {
      invalidType: 'サポートされていないファイル形式です。.pcap, .csv, .json ファイルを選択してください。',
      sizeExceeded: 'ファイルサイズが大きすぎます。100MB以下のファイルを選択してください。'
    }
  }), [])

  const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0]
    if (selectedFile) {
      // ファイル形式チェック
      const fileName = selectedFile.name.toLowerCase()
      const isValidType = fileValidation.allowedTypes.some(type => fileName.endsWith(type))

      if (!isValidType) {
        setError(fileValidation.errorMessages.invalidType)
        return
      }

      // ファイルサイズチェック
      if (selectedFile.size > fileValidation.maxSize) {
        setError(fileValidation.errorMessages.sizeExceeded)
        return
      }

      setFile(selectedFile)
      setError('')
    }
  }, [fileValidation])

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.stopPropagation()
  }, [])

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.stopPropagation()

    const droppedFile = event.dataTransfer.files[0]
    if (droppedFile) {
      const fakeEvent = {
        target: { files: [droppedFile] }
      } as unknown as React.ChangeEvent<HTMLInputElement>
      handleFileSelect(fakeEvent)
    }
  }, [handleFileSelect])

  const handleUpload = async () => {
    if (!file || !deviceId.trim()) {
      setError('デバイスIDとファイルは必須です')
      return
    }

    setUploading(true)
    setUploadProgress(0)
    setError('')

    try {
      // メタデータ構築
      const metadata = {
        session_id: sessionId.trim() || undefined,
        upload_timestamp: new Date().toISOString(),
        file_type: file.name.split('.').pop()?.toLowerCase(),
        original_size: file.size
      }

      const result = await apiClient.uploadCSIData(deviceId.trim(), file, metadata)

      setUploadProgress(100)
      onUploadComplete(result)

    } catch (err: any) {
      console.error('Upload failed:', err)
      setError(err.message || 'アップロードに失敗しました')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-medium text-gray-900">
            CSIデータアップロード
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            disabled={uploading}
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-4">
          {/* デバイスID入力 */}
          <div>
            <label htmlFor="device_id" className="block text-sm font-medium text-gray-700 mb-1">
              デバイスID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              id="device_id"
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              placeholder="例: lab-device-001"
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
              disabled={uploading || Boolean(initialDeviceId)}
            />
          </div>

          {/* セッションID入力（オプション） */}
          <div>
            <label htmlFor="session_id" className="block text-sm font-medium text-gray-700 mb-1">
              セッションID (オプション)
            </label>
            <input
              type="text"
              id="session_id"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="例: session-001"
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
              disabled={uploading}
            />
          </div>

          {/* ファイルアップロード */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              CSIデータファイル <span className="text-red-500">*</span>
            </label>
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
                uploading
                  ? 'border-gray-200 bg-gray-50'
                  : 'border-gray-300 hover:border-gray-400 cursor-pointer'
              }`}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
            >
              <input
                type="file"
                accept=".pcap,.csv,.json"
                onChange={handleFileSelect}
                className="hidden"
                id="file-input"
                disabled={uploading}
              />

              {file ? (
                <div className="space-y-2">
                  <div className="text-sm font-medium text-gray-900">
                    {file.name}
                  </div>
                  <div className="text-xs text-gray-500">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </div>
                  {!uploading && (
                    <button
                      onClick={() => setFile(null)}
                      className="text-xs text-blue-600 hover:text-blue-500"
                    >
                      変更
                    </button>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <svg className="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48">
                    <path
                      d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <div className="text-sm text-gray-600">
                    <label htmlFor="file-input" className="cursor-pointer text-blue-600 hover:text-blue-500">
                      ファイルを選択
                    </label>
                    {' '}またはドラッグ&ドロップ
                  </div>
                  <p className="text-xs text-gray-500">
                    PCAP, CSV, JSON (最大100MB)
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* アップロード進捗 */}
          {uploading && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>アップロード中...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                ></div>
              </div>
            </div>
          )}

          {/* エラー表示 */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md text-sm">
              {error}
            </div>
          )}

          {/* ボタン */}
          <div className="flex space-x-4 pt-6">
            <button
              type="button"
              onClick={onClose}
              disabled={uploading}
              className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 border border-gray-300 rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              キャンセル
            </button>
            <button
              onClick={handleUpload}
              disabled={!file || !deviceId.trim() || uploading}
              className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {uploading ? 'アップロード中...' : 'アップロード'}
            </button>
          </div>
        </div>

        {/* 注意事項 */}
        <div className="mt-6 p-4 bg-blue-50 rounded-md">
          <h4 className="text-sm font-medium text-blue-900 mb-2">
            アップロード後の処理
          </h4>
          <ol className="text-xs text-blue-800 space-y-1 list-decimal list-inside">
            <li>ファイルがサーバーに安全に保存されます</li>
            <li>自動的にCSI解析処理が開始されます</li>
            <li>解析完了後、結果がリアルタイムで通知されます</li>
            <li>データ解析画面で詳細な結果を確認できます</li>
          </ol>
        </div>
      </div>
    </div>
  )
})

export default CSIUploadModal