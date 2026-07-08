"use client";

import { useMemo, useRef, useState } from "react";
import { API_BASE } from "../upload/constants";
import { SignalChart } from "../upload/SignalChart";
import type { SignalPoint } from "../upload/types";

/** breathing_pipeline（5-1.ipynb）のサンプリング周波数 */
const PIPELINE_FS = 100;
/** rechartsの描画負荷を抑えるための表示上限点数 */
const MAX_CHART_POINTS = 2000;

async function requestAnalysis(file: File, signal: AbortSignal): Promise<number[]> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/v2/breathing/analyze`, {
    method: "POST",
    body: form,
    signal,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // JSONでないエラーレスポンスはstatusTextのまま表示する
    }
    throw new Error(`${res.status}: ${detail}`);
  }

  const data: unknown = await res.json();
  if (!Array.isArray(data) || data.some((v) => typeof v !== "number")) {
    throw new Error("サーバーから不正な解析結果が返されました");
  }
  return data as number[];
}

function toChartPoints(waveform: number[]): SignalPoint[] {
  const step = Math.max(1, Math.ceil(waveform.length / MAX_CHART_POINTS));
  const points: SignalPoint[] = [];
  for (let i = 0; i < waveform.length; i += step) {
    points.push({ time: i / PIPELINE_FS, amplitude: waveform[i] });
  }
  return points;
}

function downloadAsJson(waveform: number[], sourceName: string): void {
  const base = sourceName.replace(/\.[^.]+$/, "") || "csi";
  const blob = new Blob([JSON.stringify(waveform)], { type: "application/json" });
  const url = URL.createObjectURL(blob);

  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${base}_breathing_waveform.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function AnalyzeSection() {
  const [file, setFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waveform, setWaveform] = useState<number[] | null>(null);
  const [sourceName, setSourceName] = useState<string>("");

  const abortRef = useRef<AbortController | null>(null);

  const chartPoints = useMemo(
    () => (waveform ? toChartPoints(waveform) : []),
    [waveform],
  );

  const handleAnalyze = async () => {
    if (!file) return;

    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;

    setAnalyzing(true);
    setError(null);
    setWaveform(null);

    try {
      const result = await requestAnalysis(file, abort.signal);
      setWaveform(result);
      setSourceName(file.name);
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setError(e instanceof Error ? e.message : "解析に失敗しました");
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="rounded-2xl border border-neutral-200 bg-neutral-50 p-6 shadow-sm">
      <h2 className="mb-1 text-lg font-bold text-neutral-800">CSI呼吸解析</h2>
      <p className="mb-4 text-sm text-neutral-500">
        PicoScenes .csi ファイルをアップロードすると、呼吸波形の配列が返ります
      </p>

      <div className="flex items-center gap-3">
        <label className="flex-1 cursor-pointer">
          <span className="block rounded-lg border border-dashed border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-500 hover:border-blue-400 hover:text-blue-500">
            {file ? file.name : "ファイルを選択..."}
          </span>
          <input
            type="file"
            accept=".csi"
            className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <button
          onClick={handleAnalyze}
          disabled={!file || analyzing}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:opacity-40"
        >
          {analyzing ? "解析中..." : "解析する"}
        </button>
      </div>

      {analyzing && (
        <p className="mt-3 text-sm text-neutral-500">
          サーバーで解析しています。ファイルサイズによって数十秒かかることがあります…
        </p>
      )}

      {error && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      {waveform && (
        <div className="mt-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-neutral-600">
              解析結果: <span className="font-mono">{waveform.length.toLocaleString()}</span> サンプル
              （{(waveform.length / PIPELINE_FS).toFixed(1)} 秒 / {PIPELINE_FS}Hz）
            </p>
            <button
              onClick={() => downloadAsJson(waveform, sourceName)}
              className="rounded-lg border border-neutral-300 bg-white px-4 py-2 text-sm font-semibold text-neutral-700 transition-colors hover:bg-neutral-100"
            >
              結果をダウンロード (JSON)
            </button>
          </div>
          <SignalChart title="呼吸波形（VMD呼吸成分）" points={chartPoints} color="#16a34a" />
        </div>
      )}
    </div>
  );
}
