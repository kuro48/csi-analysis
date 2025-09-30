'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

const navigation = [
  { name: 'ダッシュボード', href: '/dashboard', icon: '📊' },
  { name: 'デバイス管理', href: '/devices', icon: '📱' },
  { name: 'リアルタイム監視', href: '/monitoring', icon: '👁️' },
  { name: '解析結果', href: '/analysis', icon: '📈' },
  { name: 'アラート', href: '/alerts', icon: '🚨' },
  { name: 'データ管理', href: '/data', icon: '💾' },
  { name: 'ユーザー管理', href: '/users', icon: '👥' },
  { name: '設定', href: '/settings', icon: '⚙️' },
]

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const pathname = usePathname()

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 flex z-40 md:hidden"
          onClick={onClose}
        >
          <div className="fixed inset-0 bg-gray-600 bg-opacity-75" />
        </div>
      )}

      {/* Sidebar */}
      <div
        className={`${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        } fixed inset-y-0 left-0 flex flex-col w-64 bg-white border-r border-gray-200 pt-5 pb-4 overflow-y-auto transition-transform duration-300 ease-in-out md:translate-x-0 md:static md:inset-0 z-40`}
      >
        {/* Logo */}
        <div className="flex items-center flex-shrink-0 px-4">
          <Link href="/" className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white text-sm font-bold">CSI</span>
            </div>
            <span className="text-lg font-semibold text-gray-900">
              監視システム
            </span>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="mt-5 flex-1 px-2 space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`${
                  isActive
                    ? 'bg-blue-50 border-r-2 border-blue-600 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                } group flex items-center px-2 py-2 text-sm font-medium rounded-md`}
              >
                <span className="mr-3 text-lg">{item.icon}</span>
                {item.name}
              </Link>
            )
          })}
        </nav>

        {/* System Status */}
        <div className="flex-shrink-0 px-4 py-4 border-t border-gray-200">
          <div className="flex items-center space-x-2">
            <div className="w-2 h-2 bg-green-500 rounded-full"></div>
            <span className="text-sm text-gray-500">システム正常</span>
          </div>
        </div>
      </div>
    </>
  )
}