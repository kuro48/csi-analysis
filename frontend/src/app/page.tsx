import Link from 'next/link'

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center justify-center min-h-screen py-12">
          {/* ヘッダー */}
          <div className="text-center mb-16">
            <div className="mb-8">
              <div className="w-20 h-20 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-6">
                <span className="text-white text-2xl font-bold">CSI</span>
              </div>
              <h1 className="text-4xl md:text-6xl font-bold text-gray-900 mb-4">
                CSI呼吸監視システム
              </h1>
              <p className="text-xl text-gray-600 max-w-2xl mx-auto">
                Wi-Fi CSI（Channel State Information）を活用した<br />
                非接触呼吸監視システム
              </p>
            </div>
          </div>

          {/* 機能カード */}
          <div className="grid md:grid-cols-3 gap-8 mb-16 max-w-4xl">
            <div className="bg-white rounded-lg shadow-md p-6 text-center">
              <div className="text-4xl mb-4">📊</div>
              <h3 className="text-lg font-semibold mb-2">リアルタイム監視</h3>
              <p className="text-gray-600 text-sm">
                CSIデータを使用した<br />リアルタイム呼吸監視
              </p>
            </div>
            <div className="bg-white rounded-lg shadow-md p-6 text-center">
              <div className="text-4xl mb-4">📱</div>
              <h3 className="text-lg font-semibold mb-2">デバイス管理</h3>
              <p className="text-gray-600 text-sm">
                Raspberry Piデバイスの<br />一元管理システム
              </p>
            </div>
            <div className="bg-white rounded-lg shadow-md p-6 text-center">
              <div className="text-4xl mb-4">📈</div>
              <h3 className="text-lg font-semibold mb-2">データ解析</h3>
              <p className="text-gray-600 text-sm">
                高精度な呼吸解析と<br />統計データの可視化
              </p>
            </div>
          </div>

          {/* CTA ボタン */}
          <div className="flex flex-col sm:flex-row gap-4">
            <Link
              href="/dashboard"
              className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-8 rounded-lg transition-colors"
            >
              ダッシュボードへ
            </Link>
            <Link
              href="/auth/login"
              className="border border-gray-300 hover:border-gray-400 text-gray-700 hover:text-gray-900 font-semibold py-3 px-8 rounded-lg transition-colors bg-white"
            >
              ログイン
            </Link>
          </div>

          {/* フッター */}
          <div className="mt-16 text-center">
            <p className="text-gray-500 text-sm">
              Version 2.5.0 | Docker対応 | 完全オープンソース
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
