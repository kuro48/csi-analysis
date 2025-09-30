'use client'

import React, { useState } from 'react'
import MainLayout from '@/components/layout/MainLayout'
import { ProtectedPage } from '@/components/auth/AuthGuard'
import { useAuth } from '@/hooks/useAuth'
import { formatJapaneseDate } from '@/utils/date'

export default function ProfilePage() {
  const { user, refreshUser } = useAuth()
  const [isEditing, setIsEditing] = useState(false)
  const [formData, setFormData] = useState({
    username: user?.username || '',
    email: user?.email || '',
  })
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setMessage('')

    try {
      // TODO: API呼び出し実装
      console.log('Profile update:', formData)

      // 仮の更新処理
      await new Promise(resolve => setTimeout(resolve, 1000))

      setMessage('プロフィールを更新しました。')
      setIsEditing(false)
      await refreshUser()
    } catch (error) {
      setMessage('プロフィールの更新に失敗しました。')
    } finally {
      setIsLoading(false)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
  }

  const handleCancel = () => {
    setFormData({
      username: user?.username || '',
      email: user?.email || '',
    })
    setIsEditing(false)
    setMessage('')
  }

  return (
    <ProtectedPage>
      <MainLayout>
        <div className="max-w-4xl">
          <div className="md:flex md:items-center md:justify-between mb-6">
            <div className="flex-1 min-w-0">
              <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                プロフィール
              </h2>
              <p className="mt-1 text-sm text-gray-500">
                アカウント情報を管理します
              </p>
            </div>
          </div>

          <div className="bg-white shadow rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              {message && (
                <div className={`mb-4 p-4 rounded-md ${
                  message.includes('失敗')
                    ? 'bg-red-50 text-red-700 border border-red-200'
                    : 'bg-green-50 text-green-700 border border-green-200'
                }`}>
                  {message}
                </div>
              )}

              <div className="space-y-6">
                {/* プロフィール写真 */}
                <div className="flex items-center space-x-6">
                  <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center">
                    <span className="text-2xl font-bold text-blue-600">
                      {user?.username?.charAt(0).toUpperCase() || 'U'}
                    </span>
                  </div>
                  <div>
                    <h3 className="text-lg font-medium text-gray-900">
                      {user?.username || 'ユーザー'}
                    </h3>
                    <p className="text-sm text-gray-500">
                      {user?.is_superuser ? '管理者' : '一般ユーザー'}
                    </p>
                  </div>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">
                  {/* ユーザー名 */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      ユーザー名
                    </label>
                    <div className="mt-1">
                      {isEditing ? (
                        <input
                          type="text"
                          name="username"
                          value={formData.username}
                          onChange={handleInputChange}
                          className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                        />
                      ) : (
                        <p className="text-sm text-gray-900 bg-gray-50 p-3 rounded-md">
                          {user?.username}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* メールアドレス */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      メールアドレス
                    </label>
                    <div className="mt-1">
                      {isEditing ? (
                        <input
                          type="email"
                          name="email"
                          value={formData.email}
                          onChange={handleInputChange}
                          className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                        />
                      ) : (
                        <p className="text-sm text-gray-900 bg-gray-50 p-3 rounded-md">
                          {user?.email}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* アカウント情報 */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-medium text-gray-700">
                        アカウント作成日
                      </label>
                      <p className="mt-1 text-sm text-gray-900 bg-gray-50 p-3 rounded-md">
                        {user?.created_at ? formatJapaneseDate(user.created_at) : '-'}
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700">
                        最終ログイン
                      </label>
                      <p className="mt-1 text-sm text-gray-900 bg-gray-50 p-3 rounded-md">
                        {user?.last_login_at ? formatJapaneseDate(user.last_login_at) : 'なし'}
                      </p>
                    </div>
                  </div>

                  {/* アカウントステータス */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      アカウントステータス
                    </label>
                    <div className="mt-1">
                      <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                        user?.is_active
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}>
                        {user?.is_active ? 'アクティブ' : '無効'}
                      </span>
                    </div>
                  </div>

                  {/* ボタン */}
                  <div className="flex justify-end space-x-3">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          onClick={handleCancel}
                          className="bg-white py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                        >
                          キャンセル
                        </button>
                        <button
                          type="submit"
                          disabled={isLoading}
                          className="bg-blue-600 py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isLoading ? '保存中...' : '保存'}
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setIsEditing(true)}
                        className="bg-blue-600 py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                      >
                        編集
                      </button>
                    )}
                  </div>
                </form>
              </div>
            </div>
          </div>

          {/* セキュリティセクション */}
          <div className="bg-white shadow rounded-lg mt-6">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
                セキュリティ
              </h3>

              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                  <div>
                    <h4 className="text-sm font-medium text-gray-900">
                      パスワード変更
                    </h4>
                    <p className="text-sm text-gray-500">
                      アカウントのセキュリティを保つため定期的にパスワードを変更してください
                    </p>
                  </div>
                  <button className="bg-white py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50">
                    変更
                  </button>
                </div>

                <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                  <div>
                    <h4 className="text-sm font-medium text-gray-900">
                      二要素認証
                    </h4>
                    <p className="text-sm text-gray-500">
                      アカウントのセキュリティを向上させるために二要素認証を有効にできます
                    </p>
                  </div>
                  <button className="bg-white py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50">
                    設定
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </MainLayout>
    </ProtectedPage>
  )
}