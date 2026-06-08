"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnalysisResultPanel } from "./upload/AnalysisResultPanel";
import { listMainCSI } from "./upload/api";
import { MetricCard } from "./upload/MetricCard";
import { StatusBadge } from "./upload/StatusBadge";
import type { CSIStatus, MainCSIResponse } from "./upload/types";

const REFRESH_INTERVAL_MS = 5000;

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function formatFileSize(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function statusLabel(status: CSIStatus): string {
  const labels: Record<CSIStatus, string> = {
    uploaded: "アップロード済み",
    processing: "解析中",
    completed: "完了",
    error: "エラー",
  };
  return labels[status] ?? status;
}

function getLatestCompleted(records: MainCSIResponse[]): MainCSIResponse | null {
  return records.find((record) => record.status === "completed") ?? null;
}

export function DeviceDashboard() {
  const [records, setRecords] = useState<MainCSIResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRecords = useCallback(async (signal?: AbortSignal) => {
    const response = await listMainCSI({ status: "all", pageSize: 20 }, signal);
    setRecords(response.csi_data);
    setSelectedId((current) => current ?? response.csi_data[0]?.id ?? null);
  }, []);

  useEffect(() => {
    const abort = new AbortController();

    async function load() {
      try {
        setError(null);
        await fetchRecords(abort.signal);
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setError((e as Error).message);
        }
      } finally {
        setLoading(false);
      }
    }

    load();
    const timer = setInterval(load, REFRESH_INTERVAL_MS);

    return () => {
      abort.abort();
      clearInterval(timer);
    };
  }, [fetchRecords]);

  const selected = useMemo(
    () => records.find((record) => record.id === selectedId) ?? records[0] ?? null,
    [records, selectedId]
  );
  const latestCompleted = getLatestCompleted(records);
  const completedCount = records.filter((record) => record.status === "completed").length;
  const processingCount = records.filter(
    (record) => record.status === "uploaded" || record.status === "processing"
  ).length;
  const devices = new Set(records.map((record) => record.device_id).filter(Boolean));

  return (
    <main className="min-h-screen bg-neutral-100 px-4 py-6 text-neutral-900 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-blue-700">CSI Edge Monitor</p>
            <h1 className="mt-1 text-2xl font-bold tracking-normal text-neutral-950 sm:text-3xl">
              エッジデバイス計測データ
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-neutral-600">
              エッジデバイスからアップロードされたCSIデータと、FFT・Wavelet・MUSIC解析結果を表示します。
            </p>
          </div>
          <Link
            href="/upload"
            className="inline-flex h-10 items-center justify-center rounded-lg bg-neutral-900 px-4 text-sm font-semibold text-white transition-colors hover:bg-neutral-700"
          >
            手動アップロード
          </Link>
        </header>

        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="最新20件" value={records.length} digits={0} />
          <MetricCard label="解析完了" value={completedCount} digits={0} />
          <MetricCard label="処理中" value={processingCount} digits={0} />
          <MetricCard label="デバイス数" value={devices.size} digits={0} />
        </section>

        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        )}

        <section className="grid gap-6 lg:grid-cols-[minmax(320px,420px)_1fr]">
          <div className="rounded-lg border border-neutral-200 bg-white shadow-sm">
            <div className="border-b border-neutral-200 px-4 py-3">
              <h2 className="text-sm font-semibold text-neutral-900">アップロード履歴</h2>
              <p className="mt-1 text-xs text-neutral-500">5秒ごとに自動更新</p>
            </div>

            <div className="max-h-[680px] overflow-y-auto p-2">
              {loading && records.length === 0 && (
                <p className="px-3 py-8 text-center text-sm text-neutral-500">読み込み中...</p>
              )}

              {!loading && records.length === 0 && (
                <p className="px-3 py-8 text-center text-sm text-neutral-500">
                  アップロードされたCSIデータはまだありません。
                </p>
              )}

              {records.map((record) => {
                const active = selected?.id === record.id;
                return (
                  <button
                    key={record.id}
                    type="button"
                    onClick={() => setSelectedId(record.id)}
                    className={`mb-2 w-full rounded-lg border p-3 text-left transition-colors ${
                      active
                        ? "border-blue-300 bg-blue-50"
                        : "border-neutral-200 bg-white hover:border-neutral-300 hover:bg-neutral-50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-neutral-900">
                          {record.device_id ?? "unknown-device"}
                        </p>
                        <p className="mt-1 truncate font-mono text-xs text-neutral-500">{record.id}</p>
                      </div>
                      <StatusBadge status={record.status} />
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-neutral-500">
                      <p>時刻: {formatDate(record.created_at)}</p>
                      <p>サイズ: {formatFileSize(record.file_size)}</p>
                      <p className="truncate">セッション: {record.session_id ?? "—"}</p>
                      <p>状態: {statusLabel(record.status)}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-6">
            <section className="rounded-lg border border-neutral-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-neutral-900">選択中の計測データ</h2>
                  {selected ? (
                    <p className="mt-1 break-all font-mono text-xs text-neutral-500">{selected.id}</p>
                  ) : (
                    <p className="mt-1 text-sm text-neutral-500">データを選択してください。</p>
                  )}
                </div>
                {selected && <StatusBadge status={selected.status} />}
              </div>

              {selected ? (
                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-lg bg-neutral-50 p-3">
                    <p className="text-xs text-neutral-500">デバイスID</p>
                    <p className="mt-1 truncate text-sm font-semibold text-neutral-900">
                      {selected.device_id ?? "—"}
                    </p>
                  </div>
                  <div className="rounded-lg bg-neutral-50 p-3">
                    <p className="text-xs text-neutral-500">セッション</p>
                    <p className="mt-1 truncate text-sm font-semibold text-neutral-900">
                      {selected.session_id ?? "—"}
                    </p>
                  </div>
                  <div className="rounded-lg bg-neutral-50 p-3">
                    <p className="text-xs text-neutral-500">アップロード時刻</p>
                    <p className="mt-1 text-sm font-semibold text-neutral-900">
                      {formatDate(selected.created_at)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-neutral-50 p-3">
                    <p className="text-xs text-neutral-500">ファイルサイズ</p>
                    <p className="mt-1 text-sm font-semibold text-neutral-900">
                      {formatFileSize(selected.file_size)}
                    </p>
                  </div>
                </div>
              ) : null}
            </section>

            {selected?.status === "completed" ? (
              <section className="rounded-lg border border-neutral-200 bg-neutral-50 p-5 shadow-sm">
                <div className="mb-4 flex flex-col gap-1">
                  <h2 className="text-lg font-semibold text-neutral-900">CSI解析結果</h2>
                  <p className="text-sm text-neutral-500">
                    呼吸数推定、ベースCSI類似度、ZKP検証、周波数スペクトル
                  </p>
                </div>
                <AnalysisResultPanel mode="main" processedData={selected.processed_data} />
              </section>
            ) : (
              <section className="rounded-lg border border-neutral-200 bg-white p-8 text-center shadow-sm">
                <p className="text-sm font-semibold text-neutral-800">
                  {selected
                    ? `${statusLabel(selected.status)}のため解析結果はまだ表示できません。`
                    : "解析結果を表示するデータがありません。"}
                </p>
                {latestCompleted && selected?.id !== latestCompleted.id && (
                  <button
                    type="button"
                    onClick={() => setSelectedId(latestCompleted.id)}
                    className="mt-4 rounded-lg border border-neutral-300 px-4 py-2 text-sm font-semibold text-neutral-700 transition-colors hover:bg-neutral-50"
                  >
                    最新の完了データを見る
                  </button>
                )}
              </section>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
