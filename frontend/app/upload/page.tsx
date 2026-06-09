import Link from "next/link";
import { UploadSection } from "./UploadSection";

export default function UploadPage() {
  return (
    <main className="min-h-screen bg-neutral-100 px-4 py-10">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-neutral-900">CSI アップロード & 解析</h1>
            <p className="mt-1 text-sm text-neutral-500">
              ベースCSI とメインCSI を個別にアップロードして解析結果を確認します
            </p>
          </div>
          <Link
            href="/"
            className="inline-flex h-10 shrink-0 items-center justify-center rounded-lg border border-neutral-300 bg-white px-4 text-sm font-semibold text-neutral-700 shadow-sm transition-colors hover:bg-neutral-50"
          >
            ホームへ戻る
          </Link>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <UploadSection mode="base" />
          <UploadSection mode="main" />
        </div>
      </div>
    </main>
  );
}
