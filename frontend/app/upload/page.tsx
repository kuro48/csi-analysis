import { UploadSection } from "./UploadSection";

export default function UploadPage() {
  return (
    <main className="min-h-screen bg-neutral-100 px-4 py-10">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-neutral-900">CSI アップロード & 解析</h1>
          <p className="mt-1 text-sm text-neutral-500">
            ベースCSI とメインCSI を個別にアップロードして解析結果を確認します
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <UploadSection mode="base" />
          <UploadSection mode="main" />
        </div>
      </div>
    </main>
  );
}
