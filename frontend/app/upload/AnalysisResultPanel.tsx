"use client";

import { useState } from "react";
import { MetricCard } from "./MetricCard";
import { SignalChart } from "./SignalChart";
import { SpectrumChart } from "./SpectrumChart";
import {
  dataframeToSpectrumPoints,
  pickBreathingBpm,
  pickSimilarityScores,
  signalDictToPoints,
  type SignalSource,
} from "./transformers";
import type { DataframeDict, ProcessedData, SignalDict, TransformZKPResult } from "./types";

interface BaseCSIData {
  mode: "base";
  fft_dataframe: DataframeDict;
  wavelet_dataframe: DataframeDict;
  music_dataframe: DataframeDict;
  raw_signal_dataframe?: SignalDict;
  filtered_signal_dataframe?: SignalDict;
}

interface MainCSIData {
  mode: "main";
  processedData: ProcessedData | null;
}

type Props = BaseCSIData | MainCSIData;

function formatTransformStatus(result: TransformZKPResult | null | undefined): string {
  if (!result) return "未生成";
  return result.is_normal ? "normal" : "abnormal";
}

function formatProofId(value: string | null | undefined): string {
  return value && value.length > 0 ? value : "未記録";
}

function BasePanel({ fft_dataframe, wavelet_dataframe, music_dataframe, raw_signal_dataframe, filtered_signal_dataframe }: BaseCSIData) {
  const fftPoints = dataframeToSpectrumPoints(fft_dataframe);
  const waveletPoints = dataframeToSpectrumPoints(wavelet_dataframe);
  const musicPoints = dataframeToSpectrumPoints(music_dataframe);
  const rawPoints = signalDictToPoints(raw_signal_dataframe ?? null);
  const filteredPoints = signalDictToPoints(filtered_signal_dataframe ?? null);

  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-neutral-400">処理過程</p>
      <SignalChart title="生CSI振幅（時系列）" points={rawPoints} color="#6366f1" />
      <SignalChart title="バンドパスフィルタ後（時系列）" points={filteredPoints} color="#f59e0b" />
      <p className="text-xs font-semibold uppercase tracking-wide text-neutral-400">周波数スペクトル</p>
      <SpectrumChart title="FFT スペクトル" points={fftPoints} />
      <SpectrumChart title="Wavelet スペクトル" points={waveletPoints} />
      <SpectrumChart title="MUSIC スペクトル" points={musicPoints} />
    </div>
  );
}

interface SignalSpectrumSectionProps {
  processedData: ProcessedData;
  source: SignalSource;
}

function SignalSpectrumSection({ processedData, source }: SignalSpectrumSectionProps) {
  const bpm = pickBreathingBpm(processedData, source);
  const hasAnyBreathingBpm = [bpm.fft, bpm.wavelet, bpm.music].some(
    (value) => value != null,
  );

  const labelSuffix = source === "phase" ? " (位相)" : " (振幅)";
  const fftDf =
    source === "phase" ? processedData.fft_phase_dataframe : processedData.fft_dataframe;
  const waveletDf =
    source === "phase"
      ? processedData.wavelet_phase_dataframe
      : processedData.wavelet_dataframe;
  const musicDf =
    source === "phase" ? processedData.music_phase_dataframe : processedData.music_dataframe;

  const fftPoints = dataframeToSpectrumPoints(fftDf ?? null);
  const waveletPoints = dataframeToSpectrumPoints(waveletDf ?? null);
  const musicPoints = dataframeToSpectrumPoints(musicDf ?? null);
  const hasAnySpectrum = fftPoints.length + waveletPoints.length + musicPoints.length > 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <MetricCard label={`FFT BPM${labelSuffix}`} value={bpm.fft} unit="BPM" />
        <MetricCard label={`Wavelet BPM${labelSuffix}`} value={bpm.wavelet} unit="BPM" />
        <MetricCard label={`MUSIC BPM${labelSuffix}`} value={bpm.music} unit="BPM" />
      </div>
      {!hasAnyBreathingBpm && (
        <p className="rounded-lg border border-neutral-200 bg-white px-4 py-3 text-sm text-neutral-500">
          {source === "phase"
            ? "位相解析の呼吸数データはありません。位相情報を含む CSI ファイルではない可能性があります。"
            : "呼吸数データはありません。"}
        </p>
      )}

      {hasAnySpectrum ? (
        <div className="space-y-3">
          <SpectrumChart title={`FFT スペクトル${labelSuffix}`} points={fftPoints} />
          <SpectrumChart title={`Wavelet スペクトル${labelSuffix}`} points={waveletPoints} />
          <SpectrumChart title={`MUSIC スペクトル${labelSuffix}`} points={musicPoints} />
        </div>
      ) : (
        source === "phase" && (
          <p className="rounded-lg border border-neutral-200 bg-white px-4 py-3 text-sm text-neutral-500">
            位相スペクトルデータはありません。
          </p>
        )
      )}
    </div>
  );
}

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function TabButton({ active, onClick, children }: TabButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        active
          ? "rounded-t-lg border border-b-0 border-neutral-300 bg-white px-4 py-2 text-sm font-semibold text-neutral-900"
          : "rounded-t-lg border border-transparent px-4 py-2 text-sm text-neutral-500 hover:text-neutral-800"
      }
    >
      {children}
    </button>
  );
}

function MainPanel({ processedData }: MainCSIData) {
  const [activeTab, setActiveTab] = useState<SignalSource>("amplitude");

  if (!processedData) return null;

  if (processedData.error) {
    return <p className="text-sm text-red-600">{processedData.error}</p>;
  }

  if (processedData.analysis) {
    const analysis = processedData.analysis;
    const circom = processedData.proofs?.python_circom;
    const zkvm = processedData.proofs?.zkvm;
    const proofLabel = (proof: typeof circom) => {
      if (!proof) return "未実行";
      if (proof.status === "failed") return `失敗: ${proof.error ?? "unknown error"}`;
      return proof.isValid
        ? proof.isNormal
          ? "valid / normal"
          : "valid / abnormal"
        : "invalid";
    };

    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <MetricCard
            label="5-1 呼吸数"
            value={analysis.breathing_rate_bpm ?? null}
            unit="BPM"
          />
          <MetricCard
            label="ピーク周波数"
            value={analysis.peak_freq_hz ?? null}
            unit="Hz"
            digits={3}
          />
          <MetricCard
            label="zkVM 呼吸数"
            value={
              zkvm?.journal?.breathing_rate_milli_bpm != null
                ? zkvm.journal.breathing_rate_milli_bpm / 1000
                : null
            }
            unit="BPM"
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-neutral-200 bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Python + Circom
            </p>
            <p className="mt-2 text-sm font-semibold text-neutral-900">{proofLabel(circom)}</p>
            <p className="mt-1 text-xs text-neutral-500">
              {circom?.method ?? "breathing_certificate"}
            </p>
          </div>
          <div className="rounded-lg border border-neutral-200 bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
              RISC Zero zkVM
            </p>
            <p className="mt-2 text-sm font-semibold text-neutral-900">{proofLabel(zkvm)}</p>
            <p className="mt-1 text-xs text-neutral-500">
              {zkvm?.journal?.algorithm_version ?? zkvm?.method ?? "5-1-fixed-v1"}
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-4 text-xs text-neutral-600">
          <p>解析パイプライン: {analysis.pipeline ?? "5-1.ipynb"}</p>
          <p className="mt-1 break-all font-mono">
            入力コミットメント: {analysis.input_commitment ?? "—"}
          </p>
          <p className="mt-2">
            一時無効: {(processedData.disabled_methods ?? []).join(", ") || "なし"}
          </p>
        </div>
      </div>
    );
  }

  const similarity = pickSimilarityScores(processedData);
  const comparison = processedData.base_csi_comparison;
  const primaryMethod = comparison?.primary_method ?? comparison?.comparison_summary?.primary_method;
  const dimensions = comparison?.data_dimensions;

  const hasPhaseData =
    processedData.fft_phase_dataframe != null ||
    processedData.wavelet_phase_dataframe != null ||
    processedData.music_phase_dataframe != null ||
    processedData.breathing_rate_phase_comparison != null;

  const rawPoints = signalDictToPoints(processedData.raw_signal ?? null);
  const filteredPoints = signalDictToPoints(processedData.filtered_signal ?? null);

  return (
    <div className="space-y-4">
      <div className="flex border-b border-neutral-300">
        <TabButton
          active={activeTab === "amplitude"}
          onClick={() => setActiveTab("amplitude")}
        >
          振幅解析
        </TabButton>
        <TabButton
          active={activeTab === "phase"}
          onClick={() => setActiveTab("phase")}
        >
          位相解析
          {!hasPhaseData && (
            <span className="ml-2 text-xs text-neutral-400">(データなし)</span>
          )}
        </TabButton>
      </div>

      <SignalSpectrumSection processedData={processedData} source={activeTab} />

      {Object.keys(similarity).length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <MetricCard label="FFT 類似度" value={similarity.fft} digits={3} />
          <MetricCard label="Wavelet 類似度" value={similarity.wavelet} digits={3} />
          <MetricCard label="MUSIC 類似度" value={similarity.music} digits={3} />
        </div>
      )}

      {comparison && (
        <div className="rounded-lg border border-neutral-200 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
                ベースCSI比較
              </p>
              <p className="mt-1 text-sm font-semibold text-neutral-900">
                {comparison.base_csi_name}
              </p>
              <p className="mt-1 break-all font-mono text-xs text-neutral-500">
                {comparison.base_csi_id}
              </p>
            </div>
            <div className="text-right text-xs text-neutral-500">
              <p>代表手法: {primaryMethod ?? "—"}</p>
              <p>検証: {comparison.is_valid ? "valid" : "not valid"}</p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 text-xs text-neutral-600 sm:grid-cols-3">
            <div className="rounded-lg bg-neutral-50 p-3">
              <p className="text-neutral-500">選択サブキャリア</p>
              <p className="mt-1 font-semibold text-neutral-900">
                {comparison.selected_subcarrier?.index ?? "—"}
              </p>
            </div>
            <div className="rounded-lg bg-neutral-50 p-3">
              <p className="text-neutral-500">周波数点</p>
              <p className="mt-1 font-semibold text-neutral-900">
                {dimensions?.num_freq_points ?? "—"}
              </p>
            </div>
            <div className="rounded-lg bg-neutral-50 p-3">
              <p className="text-neutral-500">総次元</p>
              <p className="mt-1 font-semibold text-neutral-900">
                {dimensions?.total_dimensions ?? "—"}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-neutral-200 bg-white p-4">
        <p className="text-sm font-semibold text-neutral-800">
          ZKP / ブロックチェーン記録 (振幅ベース)
        </p>
        <div className="mt-3 grid gap-3 text-xs text-neutral-600 sm:grid-cols-3">
          <div className="rounded-lg bg-neutral-50 p-3">
            <p className="text-neutral-500">FFT Proof ID</p>
            <p className="mt-1 break-all font-mono text-neutral-900">
              {comparison ? formatProofId(processedData.blockchain_proof_id) : "未生成"}
            </p>
          </div>
          <div className="rounded-lg bg-neutral-50 p-3">
            <p className="text-neutral-500">Wavelet</p>
            <p className="mt-1 font-semibold text-neutral-900">
              {formatTransformStatus(processedData.wavelet_zkp)}
            </p>
            <p className="mt-1 break-all font-mono">
              {formatProofId(processedData.wavelet_zkp?.proof_id)}
            </p>
          </div>
          <div className="rounded-lg bg-neutral-50 p-3">
            <p className="text-neutral-500">MUSIC</p>
            <p className="mt-1 font-semibold text-neutral-900">
              {formatTransformStatus(processedData.music_zkp)}
            </p>
            <p className="mt-1 break-all font-mono">
              {formatProofId(processedData.music_zkp?.proof_id)}
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-neutral-400">処理過程</p>
        <SignalChart title="生CSI振幅（時系列）" points={rawPoints} color="#6366f1" />
        <SignalChart title="バンドパスフィルタ後（時系列）" points={filteredPoints} color="#f59e0b" />
      </div>
    </div>
  );
}

export function AnalysisResultPanel(props: Props) {
  if (props.mode === "base") return <BasePanel {...props} />;
  return <MainPanel {...props} />;
}
