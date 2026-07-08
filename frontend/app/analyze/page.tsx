import Link from "next/link";
import { AnalyzeSection } from "./AnalyzeSection";

export default function AnalyzePage() {
  return (
    <main className="min-h-screen bg-neutral-100 px-4 py-10">
      <div className="mx-auto max-w-4xl">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-neutral-900">CSI呼吸解析（簡易版）</h1>
            <p className="mt-1 text-sm text-neutral-500">
              CSIファイルをアップロードすると呼吸波形を解析し、結果の配列を返します
            </p>
          </div>
          <Link
            href="/"
            className="inline-flex h-10 shrink-0 items-center justify-center rounded-lg border border-neutral-300 bg-white px-4 text-sm font-semibold text-neutral-700 shadow-sm transition-colors hover:bg-neutral-50"
          >
            ホームへ戻る
          </Link>
        </div>

        <AnalyzeSection />
      </div>
    </main>
  );
}
