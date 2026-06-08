import type { CSIStatus } from "./types";

const CONFIG: Record<CSIStatus, { label: string; cls: string }> = {
  uploaded: { label: "アップロード済み", cls: "bg-gray-100 text-gray-600" },
  processing: { label: "解析中...", cls: "bg-blue-100 text-blue-700 animate-pulse" },
  completed: { label: "完了", cls: "bg-green-100 text-green-700" },
  error: { label: "エラー", cls: "bg-red-100 text-red-700" },
};

export function StatusBadge({ status }: { status: CSIStatus }) {
  const { label, cls } = CONFIG[status] ?? CONFIG.uploaded;
  return (
    <span className={`inline-block rounded-full px-3 py-1 text-xs font-semibold ${cls}`}>
      {label}
    </span>
  );
}
