import Link from "next/link";
import { UploadSection } from "./UploadSection";

export default function UploadPage() {
  return (
    <main className="min-h-screen bg-neutral-100 px-4 py-10">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-teal-700">Persistent Analysis</p>
            <h1 className="mt-1 text-2xl font-bold text-neutral-900">CSIアップロード・解析</h1>
            <p className="mt-1 text-sm text-neutral-500">
              解析結果を保存し、5-1呼吸推定と並列証明の進行を追跡します
            </p>
          </div>
          <Link
            href="/"
            className="inline-flex h-10 shrink-0 items-center justify-center rounded-lg border border-neutral-300 bg-white px-4 text-sm font-semibold text-neutral-700 shadow-sm transition-colors hover:bg-neutral-50"
          >
            ホームへ戻る
          </Link>
        </div>

        <UploadSection />
      </div>
    </main>
  );
}
