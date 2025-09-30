'use client'

import { useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'

interface AuthGuardProps {
  children: React.ReactNode
  requireAuth?: boolean
  redirectTo?: string
}

export default function AuthGuard({
  children,
  requireAuth = true,
  redirectTo = '/auth/login'
}: AuthGuardProps) {
  const { isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (isLoading) return

    if (requireAuth && !isAuthenticated) {
      // 認証が必要だが未認証の場合
      const currentPath = encodeURIComponent(pathname)
      router.push(`${redirectTo}?redirect=${currentPath}`)
      return
    }

    if (!requireAuth && isAuthenticated) {
      // 認証が不要だが認証済みの場合（ログインページ等）
      router.push('/dashboard')
      return
    }
  }, [isAuthenticated, isLoading, requireAuth, router, pathname, redirectTo])

  // ローディング中
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
          <p className="text-gray-600">読み込み中...</p>
        </div>
      </div>
    )
  }

  // 認証が必要だが未認証の場合
  if (requireAuth && !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="text-6xl mb-4">🔒</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">認証が必要です</h1>
          <p className="text-gray-600 mb-4">このページにアクセスするにはログインが必要です。</p>
          <button
            onClick={() => router.push(redirectTo)}
            className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg"
          >
            ログインページへ
          </button>
        </div>
      </div>
    )
  }

  // 認証が不要だが認証済みの場合
  if (!requireAuth && isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
          <p className="text-gray-600">リダイレクト中...</p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}

// 認証が必要なページ用のラッパーコンポーネント
export function ProtectedPage({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard requireAuth={true}>
      {children}
    </AuthGuard>
  )
}

// 認証が不要（ログインページ等）なページ用のラッパーコンポーネント
export function PublicPage({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard requireAuth={false}>
      {children}
    </AuthGuard>
  )
}