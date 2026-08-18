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
  waveformToSignalPoints,
  type SignalSource,
} from "./transformers";
import type {
  ProcessedData,
  TransformZKPResult,
  VerifiableProofResult,
} from "./types";

interface MainCSIData {
  processedData: ProcessedData | null;
}

function formatTransformStatus(result: TransformZKPResult | null | undefined): string {
  if (!result) return "未生成";
  return result.is_normal ? "normal" : "abnormal";
}

function formatProofId(value: string | null | undefined): string {
  return value && value.length > 0 ? value : "未記録";
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return value != null && isFinite(value) ? value.toFixed(digits) : "—";
}

function proofNormality(proof: VerifiableProofResult | undefined): boolean | undefined {
  return proof?.isNormal ?? proof?.journal?.is_normal;
}

function ProofCard({
  title,
  proof,
  fallbackMethod,
}: {
  title: string;
  proof: VerifiableProofResult | undefined;
  fallbackMethod: string;
}) {
  const completed = proof?.status === "completed";
  const disabled = proof?.status === "disabled";
  const valid = completed && proof.isValid === true;
  const normal = proofNormality(proof);

  return (
    <article className="rounded-lg border border-neutral-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-neutral-900">{title}</h3>
          <p className="mt-1 font-mono text-xs text-neutral-500">
            {proof?.journal?.algorithm_version ?? proof?.method ?? fallbackMethod}
          </p>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
            valid
              ? "bg-emerald-100 text-emerald-800"
              : completed
                ? "bg-red-100 text-red-700"
                : proof?.status === "failed"
                  ? "bg-red-100 text-red-700"
                  : "bg-neutral-100 text-neutral-600"
          }`}
        >
          {valid
            ? "証明有効"
            : completed
              ? "証明無効"
              : proof?.status === "failed"
                ? "生成失敗"
                : disabled
                  ? "設定で停止中"
                  : "未実行"}
        </span>
      </div>

      {completed && (
        <div className="mt-4 flex items-center justify-between border-t border-neutral-100 pt-3">
          <span className="text-xs text-neutral-500">回路内の呼吸判定</span>
          <span className={`text-sm font-semibold ${normal ? "text-emerald-700" : "text-amber-700"}`}>
            {normal == null ? "判定なし" : normal ? "正常帯域" : "正常帯域外"}
          </span>
        </div>
      )}

      {proof?.status === "failed" && (
        <p className="mt-3 break-words rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
          {proof.error ?? proof.error_type ?? "証明生成に失敗しました"}
        </p>
      )}
    </article>
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
    const lombCircom = processedData.proofs?.lomb_scargle_circom;
    const zkvm = processedData.proofs?.zkvm;
    const lomb = analysis.lomb_scargle;
    const comparison = analysis.algorithm_comparison;
    const bpmEvaluation = processedData.bpm_evaluation;
    const waveformPoints = waveformToSignalPoints(analysis.respiration_waveform);
    const zkvmBpm =
      zkvm?.journal?.breathing_rate_milli_bpm != null
        ? zkvm.journal.breathing_rate_milli_bpm / 1000
        : null;
    const diagnostics = analysis.certificate_diagnostics;
    const resultStatus = processedData.status ?? "completed";
    const statusConfig = {
      completed: { label: "解析・証明完了", cls: "bg-emerald-100 text-emerald-800" },
      partial: { label: "一部検証完了", cls: "bg-amber-100 text-amber-800" },
      failed: { label: "検証失敗", cls: "bg-red-100 text-red-700" },
    }[resultStatus];

    return (
      <div className="space-y-6">
        <div className="flex flex-col gap-3 border-b border-neutral-200 pb-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-neutral-500">Verifiable breathing analysis</p>
            <h2 className="mt-1 text-lg font-semibold text-neutral-950">呼吸解析アルゴリズム比較</h2>
          </div>
          <span className={`w-fit rounded-full px-3 py-1 text-xs font-semibold ${statusConfig.cls}`}>
            {statusConfig.label}
          </span>
        </div>

        <ol className="grid grid-cols-2 gap-x-3 gap-y-4 border-b border-neutral-200 pb-5 text-xs text-neutral-600 sm:grid-cols-4">
          {["CSI読込・SNR選択", "帯域抽出・PCA", "VMD呼吸成分選択", "Circom証明"].map(
            (stage, index) => (
              <li key={stage} className="flex items-center gap-2">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-neutral-900 font-semibold text-white">
                  {index + 1}
                </span>
                <span>{stage}</span>
              </li>
            ),
          )}
        </ol>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="推定呼吸数"
            value={analysis.breathing_rate_bpm ?? null}
            unit="BPM"
          />
          <MetricCard
            label="ピーク周波数"
            value={analysis.peak_freq_hz ?? null}
            unit="Hz"
            digits={3}
          />
          <MetricCard label="選択PC" value={analysis.selected_pc} digits={0} />
          <MetricCard label="選択VMDモード" value={analysis.selected_vmd_mode} digits={0} />
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold text-neutral-900">推定値の比較</h3>
          <div className={`grid gap-3 sm:grid-cols-2 ${bpmEvaluation ? "xl:grid-cols-5" : "xl:grid-cols-4"}`}>
            {bpmEvaluation && (
              <MetricCard label="正解" value={bpmEvaluation.ground_truth_bpm} unit="BPM" />
            )}
            <MetricCard
              label="現行 5-1"
              value={comparison?.current_breathing_rate_bpm ?? analysis.breathing_rate_bpm ?? null}
              unit="BPM"
            />
            <MetricCard
              label="Lomb–Scargle"
              value={comparison?.lomb_scargle_breathing_rate_bpm ?? lomb?.breathing_rate_bpm ?? null}
              unit="BPM"
            />
            <MetricCard label="推定差" value={comparison?.absolute_difference_bpm ?? null} unit="BPM" />
            <MetricCard label="LS 全帯域ピーク" value={lomb?.global_peak_bpm ?? null} unit="BPM" />
          </div>
          {lomb?.status === "failed" && (
            <p className="mt-2 text-xs text-red-600">Lomb–Scargle解析失敗: {lomb.error ?? "不明なエラー"}</p>
          )}
          {lomb?.status === "completed" && (
            <p className="mt-2 text-xs text-neutral-500">
              不均一時刻を直接解析 / 平均サンプリング {formatNumber(lomb.actual_sampling_rate_hz, 2)} Hz /
              時刻間隔CV {formatNumber(lomb.sampling_interval_cv, 3)}
            </p>
          )}
        </div>

        <SignalChart title="VMDで抽出した呼吸波形" points={waveformPoints} color="#0f766e" />

        <div>
          <h3 className="mb-3 text-sm font-semibold text-neutral-900">証明</h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <ProofCard title="Python + Circom" proof={circom} fallbackMethod="breathing_certificate" />
            <ProofCard
              title="Lomb–Scargle + Circom"
              proof={lombCircom}
              fallbackMethod="lomb_scargle_periodogram_certificate"
            />
            {zkvm?.status !== "disabled" && (
              <ProofCard title="RISC Zero zkVM" proof={zkvm} fallbackMethod="5-1-fixed-v1" />
            )}
          </div>
          {zkvm?.status === "disabled" && (
            <p className="mt-2 text-xs text-neutral-500">RISC Zero zkVMは現在の処理経路では無効です。</p>
          )}
          {zkvmBpm != null && (
            <p className="mt-2 text-xs text-neutral-500">
              zkVM再計算: {formatNumber(zkvmBpm, 3)} BPM
              {analysis.breathing_rate_bpm != null &&
                ` / 差分 ${formatNumber(Math.abs(analysis.breathing_rate_bpm - zkvmBpm), 3)} BPM`}
            </p>
          )}
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold text-neutral-900">解析データ</h3>
          <dl className="grid grid-cols-2 border-y border-neutral-200 text-sm sm:grid-cols-4">
            <div className="border-b border-neutral-100 px-3 py-3 sm:border-b-0 sm:border-r">
              <dt className="text-xs text-neutral-500">サンプル数</dt>
              <dd className="mt-1 font-semibold text-neutral-900">{analysis.n_samples?.toLocaleString() ?? "—"}</dd>
            </div>
            <div className="border-b border-neutral-100 px-3 py-3 sm:border-b-0 sm:border-r">
              <dt className="text-xs text-neutral-500">選択サブキャリア</dt>
              <dd className="mt-1 font-semibold text-neutral-900">
                {analysis.n_subcarriers_selected ?? "—"} / {analysis.n_subcarriers_total ?? "—"}
              </dd>
            </div>
            <div className="px-3 py-3 sm:border-r">
              <dt className="text-xs text-neutral-500">判定BPM範囲</dt>
              <dd className="mt-1 font-semibold text-neutral-900">
                {analysis.bpm_range ? `${analysis.bpm_range.min}–${analysis.bpm_range.max}` : "—"}
              </dd>
            </div>
            <div className="px-3 py-3">
              <dt className="text-xs text-neutral-500">解析時間</dt>
              <dd className="mt-1 font-semibold text-neutral-900">
                {analysis.processing_time_seconds != null
                  ? `${formatNumber(analysis.processing_time_seconds, 2)} 秒`
                  : "—"}
              </dd>
            </div>
          </dl>
        </div>

        {analysis.vmd_mode_summaries && analysis.vmd_mode_summaries.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-neutral-200">
            <div className="border-b border-neutral-200 bg-neutral-50 px-4 py-3">
              <h3 className="text-sm font-semibold text-neutral-900">VMDモード評価</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-xs">
                <thead className="bg-white text-neutral-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">モード</th>
                    <th className="px-4 py-2 font-medium">ピーク周波数</th>
                    <th className="px-4 py-2 font-medium">呼吸数</th>
                    <th className="px-4 py-2 font-medium">ピーク比</th>
                    <th className="px-4 py-2 font-medium">帯域判定</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100 bg-white text-neutral-700">
                  {analysis.vmd_mode_summaries.map((mode) => (
                    <tr key={mode.mode} className={mode.mode === analysis.selected_vmd_mode ? "bg-teal-50" : ""}>
                      <td className="px-4 py-2.5 font-semibold">Mode {mode.mode}</td>
                      <td className="px-4 py-2.5">{formatNumber(mode.global_peak_freq_hz, 3)} Hz</td>
                      <td className="px-4 py-2.5">{formatNumber(mode.global_peak_bpm, 1)} BPM</td>
                      <td className="px-4 py-2.5">{formatNumber(mode.global_peak_ratio, 3)}</td>
                      <td className="px-4 py-2.5">{mode.is_valid ? "範囲内" : "範囲外"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {diagnostics && (
          <div>
            <h3 className="mb-3 text-sm font-semibold text-neutral-900">Circom証明書診断</h3>
            <div className="grid gap-3 text-xs sm:grid-cols-2">
              <div className="rounded-lg border border-neutral-200 bg-white p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-neutral-500">VMD再構成誤差比</span>
                  <span className={diagnostics.recon_ok ? "font-semibold text-emerald-700" : "font-semibold text-red-700"}>
                    {diagnostics.recon_ok ? "基準内" : "基準外"}
                  </span>
                </div>
                <p className="mt-2 font-mono text-neutral-800">
                  {formatNumber(diagnostics.recon_error_ratio, 4)} / 上限 {formatNumber(diagnostics.recon_error_ratio_threshold, 4)}
                </p>
              </div>
              <div className="rounded-lg border border-neutral-200 bg-white p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-neutral-500">狭帯域ピーク比</span>
                  <span className={diagnostics.narrow_ok ? "font-semibold text-emerald-700" : "font-semibold text-red-700"}>
                    {diagnostics.narrow_ok ? "基準内" : "基準外"}
                  </span>
                </div>
                <p className="mt-2 font-mono text-neutral-800">
                  {formatNumber(diagnostics.narrow_ratio, 4)} / 下限 {formatNumber(diagnostics.narrow_ratio_threshold, 4)}
                </p>
              </div>
            </div>
          </div>
        )}

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

export function AnalysisResultPanel(props: MainCSIData) {
  return <MainPanel {...props} />;
}
