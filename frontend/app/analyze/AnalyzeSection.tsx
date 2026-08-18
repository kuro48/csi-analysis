"use client";

import { useEffect, useRef, useState } from "react";
import { AnalysisResultPanel } from "../upload/AnalysisResultPanel";
import { API_BASE } from "../upload/constants";
import type { ProcessedData } from "../upload/types";

async function requestAnalysis(file: File, signal: AbortSignal): Promise<ProcessedData> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${API_BASE}/api/v2/breathing/analyze-verifiable`, {
    method: "POST",
    body: form,
    signal,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep statusText for non-JSON responses.
    }
    throw new Error(`${response.status}: ${detail}`);
  }

  const data = (await response.json()) as ProcessedData;
  if (!data.analysis || !data.proofs || !data.status) {
    throw new Error("サーバーから不正な解析結果が返されました");
  }
  return data;
}

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function downloadResult(result: ProcessedData, sourceName: string): void {
  const base = sourceName.replace(/\.[^.]+$/, "") || "csi";
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${base}_verifiable_breathing.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function AnalyzeSection() {
  const [file, setFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessedData | null>(null);
  const [sourceName, setSourceName] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState<number | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const startedAtRef = useRef(0);

  useEffect(() => () => abortRef.current?.abort(), []);

  const handleAnalyze = async () => {
    if (!file) return;

    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;
    startedAtRef.current = Date.now();

    setAnalyzing(true);
    setError(null);
    setResult(null);
    setElapsedSeconds(null);

    try {
      const analysis = await requestAnalysis(file, abort.signal);
      setResult(analysis);
      setSourceName(file.name);
    } catch (cause: unknown) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof Error ? cause.message : "解析に失敗しました");
    } finally {
      if (!abort.signal.aborted) {
        setElapsedSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
        setAnalyzing(false);
      }
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-neutral-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-semibold text-neutral-900">PicoScenes CSIを解析</h2>
          <p className="text-sm text-neutral-500">
            現行5-1方式とLomb–Scargle方式を比較し、それぞれのCircom判定を生成します
          </p>
        </div>

        <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="min-w-0 flex-1 cursor-pointer">
            <span className="block truncate rounded-lg border border-dashed border-neutral-300 bg-neutral-50 px-3 py-2.5 text-sm text-neutral-600 hover:border-teal-500 hover:text-teal-700">
              {file ? file.name : ".csiファイルを選択"}
            </span>
            <input
              type="file"
              accept=".csi"
              className="sr-only"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setResult(null);
                setError(null);
              }}
            />
          </label>
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={!file || analyzing}
            className="h-10 shrink-0 rounded-lg bg-teal-700 px-5 text-sm font-semibold text-white transition-colors hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {analyzing ? "解析・証明生成中..." : "解析を開始"}
          </button>
        </div>

        {file && (
          <p className="mt-2 text-xs text-neutral-500">
            {formatFileSize(file.size)} / PicoScenes .csi
          </p>
        )}

        {analyzing && (
          <div className="mt-4 border-l-2 border-teal-600 pl-3">
            <p className="text-sm font-medium text-neutral-800">5-1解析とCircom証明を実行中</p>
            <p className="mt-1 text-xs text-neutral-500">
              ファイルサイズによって解析に時間がかかることがあります。
            </p>
          </div>
        )}

        {error && (
          <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}
      </section>

      {result && (
        <section className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-neutral-600">
              {sourceName} / 所要時間 {elapsedSeconds ?? 0}秒
            </p>
            <button
              type="button"
              onClick={() => downloadResult(result, sourceName)}
              className="h-9 w-fit rounded-lg border border-neutral-300 bg-white px-4 text-sm font-semibold text-neutral-700 transition-colors hover:bg-neutral-50"
            >
              JSONを保存
            </button>
          </div>
          <AnalysisResultPanel processedData={result} />
        </section>
      )}
    </div>
  );
}
