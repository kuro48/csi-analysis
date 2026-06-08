"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { uploadBaseCSI, getBaseCSI, uploadMainCSI, getMainCSI } from "./api";
import { AnalysisResultPanel } from "./AnalysisResultPanel";
import { StatusBadge } from "./StatusBadge";
import { POLL_INTERVAL_MS, POLL_TIMEOUT_MS, TERMINAL_STATUSES } from "./constants";
import type { BaseCSIResponse, CSIStatus, MainCSIResponse } from "./types";

type Mode = "base" | "main";

interface Props {
  mode: Mode;
}

const LABELS: Record<Mode, { title: string; accept: string }> = {
  base: { title: "ベースCSI", accept: ".pcap,.pcapng,.cap,.csi,.csv" },
  main: { title: "メインCSI", accept: ".pcap,.pcapng,.cap,.csi,.csv" },
};

export function UploadSection({ mode }: Props) {
  const { title, accept } = LABELS[mode];

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<CSIStatus | null>(null);
  const [baseRecord, setBaseRecord] = useState<BaseCSIResponse | null>(null);
  const [mainRecord, setMainRecord] = useState<MainCSIResponse | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedAtRef = useRef<number>(0);
  const pollRef = useRef<(id: string, abort: AbortController) => Promise<void>>(async () => {});

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const poll = useCallback(
    async (id: string, abort: AbortController) => {
      if (Date.now() - startedAtRef.current > POLL_TIMEOUT_MS) {
        setError("タイムアウト: 解析に時間がかかりすぎています");
        return;
      }

      try {
        if (mode === "base") {
          const rec = await getBaseCSI(id, abort.signal);
          setBaseRecord(rec);
          setStatus(rec.status as CSIStatus);
          if (!TERMINAL_STATUSES.includes(rec.status as typeof TERMINAL_STATUSES[number])) {
            timerRef.current = setTimeout(() => pollRef.current(id, abort), POLL_INTERVAL_MS);
          }
        } else {
          const rec = await getMainCSI(id, abort.signal);
          setMainRecord(rec);
          setStatus(rec.status as CSIStatus);
          if (!TERMINAL_STATUSES.includes(rec.status as typeof TERMINAL_STATUSES[number])) {
            timerRef.current = setTimeout(() => pollRef.current(id, abort), POLL_INTERVAL_MS);
          }
        }
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setError((e as Error).message);
        }
      }
    },
    [mode]
  );

  useEffect(() => {
    pollRef.current = poll;
  }, [poll]);

  useEffect(() => {
    return () => {
      clearTimer();
      abortRef.current?.abort();
    };
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    clearTimer();
    abortRef.current?.abort();

    const abort = new AbortController();
    abortRef.current = abort;
    startedAtRef.current = Date.now();

    setUploading(true);
    setError(null);
    setStatus(null);
    setBaseRecord(null);
    setMainRecord(null);

    try {
      if (mode === "base") {
        const rec = await uploadBaseCSI(file, abort.signal);
        setBaseRecord(rec);
        setStatus(rec.status as CSIStatus);
        if (!TERMINAL_STATUSES.includes(rec.status as typeof TERMINAL_STATUSES[number])) {
          timerRef.current = setTimeout(() => poll(rec.id, abort), POLL_INTERVAL_MS);
        }
      } else {
        const rec = await uploadMainCSI(file, abort.signal);
        setMainRecord(rec);
        setStatus(rec.status as CSIStatus);
        if (!TERMINAL_STATUSES.includes(rec.status as typeof TERMINAL_STATUSES[number])) {
          timerRef.current = setTimeout(() => poll(rec.id, abort), POLL_INTERVAL_MS);
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError((e as Error).message);
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="rounded-2xl border border-neutral-200 bg-neutral-50 p-6 shadow-sm">
      <h2 className="mb-4 text-lg font-bold text-neutral-800">{title}</h2>

      <div className="flex items-center gap-3">
        <label className="flex-1 cursor-pointer">
          <span className="block rounded-lg border border-dashed border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-500 hover:border-blue-400 hover:text-blue-500">
            {file ? file.name : "ファイルを選択..."}
          </span>
          <input
            type="file"
            accept={accept}
            className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40 hover:bg-blue-700 transition-colors"
        >
          {uploading ? "送信中..." : "アップロード"}
        </button>
      </div>

      {status && (
        <div className="mt-3">
          <StatusBadge status={status} />
        </div>
      )}

      {error && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      {status === "completed" && mode === "base" && baseRecord && (
        <div className="mt-4 space-y-3">
          <div className="text-xs text-neutral-500 space-y-1">
            <p>ID: <span className="font-mono">{baseRecord.id}</span></p>
            {baseRecord.source_pcap_size && (
              <p>サイズ: {(baseRecord.source_pcap_size / 1024).toFixed(1)} KB</p>
            )}
          </div>
          <AnalysisResultPanel
            mode="base"
            fft_dataframe={baseRecord.fft_dataframe}
            wavelet_dataframe={baseRecord.wavelet_dataframe}
            music_dataframe={baseRecord.music_dataframe}
          />
        </div>
      )}

      {status === "completed" && mode === "main" && mainRecord && (
        <div className="mt-4">
          <AnalysisResultPanel mode="main" processedData={mainRecord.processed_data} />
        </div>
      )}
    </div>
  );
}
