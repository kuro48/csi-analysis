'use client'

import { useState, useEffect, useContext, createContext, ReactNode } from 'react'
import { api } from '@/services/api'
import { User } from '@/types'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

// 認証プロバイダーコンポーネント
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const isAuthenticated = !!user

  // 初期化時にローカルストレージからトークンをチェック
  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('access_token')
      if (token) {
        try {
          const currentUser = await api.auth.getCurrentUser()
          setUser(currentUser)
        } catch (error) {
          console.error('Failed to fetch user:', error)
          // トークンが無効な場合は削除
          localStorage.removeItem('access_token')
        }
      }
      setIsLoading(false)
    }

    initAuth()
  }, [])

  // ログイン処理
  const login = async (username: string, password: string) => {
    try {
      await api.auth.login(username, password)
      const currentUser = await api.auth.getCurrentUser()
      setUser(currentUser)
    } catch (error) {
      console.error('Login failed:', error)
      throw error
    }
  }

  // ログアウト処理
  const logout = async () => {
    try {
      await api.auth.logout()
    } catch (error) {
      console.error('Logout failed:', error)
    } finally {
      setUser(null)
      localStorage.removeItem('access_token')
    }
  }

  // ユーザー登録処理
  const register = async (username: string, email: string, password: string) => {
    try {
      await api.auth.register(username, email, password)
      // 登録後は自動ログインしない（メール認証等が必要な場合を考慮）
    } catch (error) {
      console.error('Registration failed:', error)
      throw error
    }
  }

  // ユーザー情報の再取得
  const refreshUser = async () => {
    if (!isAuthenticated) return

    try {
      const currentUser = await api.auth.getCurrentUser()
      setUser(currentUser)
    } catch (error) {
      console.error('Failed to refresh user:', error)
      // ユーザー情報の取得に失敗した場合はログアウト
      await logout()
    }
  }

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated,
    login,
    logout,
    register,
    refreshUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// 認証フック
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (!context) {
    console.error('useAuth must be used within an AuthProvider')
    return {
      user: null,
      isLoading: false,
      isAuthenticated: false,
      login: async () => {},
      logout: async () => {},
      register: async () => {},
      refreshUser: async () => {},
    }
  }
  return context
}

// 認証が必要なページで使用するフック
export function useRequireAuth() {
  const auth = useAuth()

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      // 認証が必要なページで未認証の場合はログインページへリダイレクト
      window.location.href = '/auth/login?redirect=' + encodeURIComponent(window.location.pathname)
    }
  }, [auth.isLoading, auth.isAuthenticated])

  return auth
}