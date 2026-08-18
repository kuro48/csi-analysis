"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getMainCSI, uploadMainCSI } from "./api";
import { AnalysisResultPanel } from "./AnalysisResultPanel";
import { GroundTruthBpmEditor } from "./GroundTruthBpmEditor";
import { StatusBadge } from "./StatusBadge";
import { POLL_INTERVAL_MS, POLL_TIMEOUT_MS, TERMINAL_STATUSES } from "./constants";
import type { CSIStatus, MainCSIResponse } from "./types";

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}秒`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return remainingSeconds > 0 ? `${minutes}分${remainingSeconds}秒` : `${minutes}分`;
}

export function UploadSection() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<CSIStatus | null>(null);
  const [record, setRecord] = useState<MainCSIResponse | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tickerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAtRef = useRef(0);
  const pollRef = useRef<(id: string, abort: AbortController) => Promise<void>>(async () => {});

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const clearTicker = () => {
    if (tickerRef.current) {
      clearInterval(tickerRef.current);
      tickerRef.current = null;
    }
  };

  const poll = useCallback(async (id: string, abort: AbortController) => {
    if (Date.now() - startedAtRef.current > POLL_TIMEOUT_MS) {
      clearTicker();
      setError("タイムアウト: 解析に時間がかかりすぎています");
      return;
    }

    try {
      const nextRecord = await getMainCSI(id, abort.signal);
      setRecord(nextRecord);
      setStatus(nextRecord.status);
      if (TERMINAL_STATUSES.includes(nextRecord.status as (typeof TERMINAL_STATUSES)[number])) {
        if (tickerRef.current) {
          clearInterval(tickerRef.current);
          tickerRef.current = null;
        }
        setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
      } else {
        timerRef.current = setTimeout(
          () => pollRef.current(nextRecord.id, abort),
          POLL_INTERVAL_MS,
        );
      }
    } catch (cause) {
      if ((cause as Error).name !== "AbortError") {
        clearTicker();
        setError((cause as Error).message);
      }
    }
  }, []);

  useEffect(() => {
    pollRef.current = poll;
  }, [poll]);

  useEffect(() => {
    return () => {
      clearTimer();
      clearTicker();
      abortRef.current?.abort();
    };
  }, []);

  const handleUpload = async () => {
    if (!file) return;

    clearTimer();
    clearTicker();
    abortRef.current?.abort();

    const abort = new AbortController();
    abortRef.current = abort;
    startedAtRef.current = Date.now();

    setUploading(true);
    setError(null);
    setStatus(null);
    setRecord(null);
    setElapsed(null);

    try {
      const nextRecord = await uploadMainCSI(file, abort.signal);
      tickerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
      }, 1000);
      setRecord(nextRecord);
      setStatus(nextRecord.status);
      if (TERMINAL_STATUSES.includes(nextRecord.status as (typeof TERMINAL_STATUSES)[number])) {
        clearTicker();
        setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
      } else {
        timerRef.current = setTimeout(
          () => pollRef.current(nextRecord.id, abort),
          POLL_INTERVAL_MS,
        );
      }
    } catch (cause) {
      if ((cause as Error).name !== "AbortError") {
        setError((cause as Error).message);
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-5 shadow-sm sm:p-6">
      <h2 className="text-lg font-semibold text-neutral-900">5-1 検証可能呼吸解析</h2>
      <p className="mt-1 mb-4 text-sm text-neutral-500">
        PicoScenes CSIを保存し、5-1解析とCircom証明を実行します
      </p>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="min-w-0 flex-1 cursor-pointer">
          <span className="mb-1 block text-xs font-semibold text-neutral-700">CSIファイル</span>
          <span className="block truncate rounded-lg border border-dashed border-neutral-300 bg-neutral-50 px-3 py-2.5 text-sm text-neutral-600 hover:border-teal-500 hover:text-teal-700">
            {file ? file.name : ".csiファイルを選択"}
          </span>
          <input
            type="file"
            accept=".csi"
            className="sr-only"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError(null);
              setRecord(null);
              setStatus(null);
            }}
          />
        </label>
        <button
          type="button"
          onClick={handleUpload}
          disabled={!file || uploading}
          className="h-10 shrink-0 rounded-lg bg-teal-700 px-5 text-sm font-semibold text-white transition-colors hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {uploading ? "送信中..." : "アップロードして解析"}
        </button>
      </div>

      {status && (
        <div className="mt-3 flex items-center gap-2">
          <StatusBadge status={status} />
          {record?.ground_truth_bpm != null && (
            <span className="text-xs font-semibold text-teal-700">正解 {record.ground_truth_bpm} BPM</span>
          )}
          {elapsed !== null && (
            <span className="text-xs text-neutral-500">
              {TERMINAL_STATUSES.includes(status as (typeof TERMINAL_STATUSES)[number])
                ? `(${formatElapsed(elapsed)})`
                : `(${formatElapsed(elapsed)}経過)`}
            </span>
          )}
        </div>
      )}

      {record && (
        <div className="mt-4">
          <GroundTruthBpmEditor
            key={`${record.id}:${record.ground_truth_bpm ?? "unset"}`}
            recordId={record.id}
            groundTruthBpm={record.ground_truth_bpm}
            onSaved={(updated) => {
              setRecord(updated);
              setStatus(updated.status);
            }}
          />
        </div>
      )}

      {error && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      {status === "error" && record?.processed_data?.error && !error && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {record.processed_data.error}
        </p>
      )}

      {status === "completed" && record && (
        <div className="mt-6 border-t border-neutral-200 pt-6">
          <AnalysisResultPanel processedData={record.processed_data} />
        </div>
      )}
    </section>
  );
}
