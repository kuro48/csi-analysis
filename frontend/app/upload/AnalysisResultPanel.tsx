"use client";

import { API_BASE } from "./constants";
import { MetricCard } from "./MetricCard";
import { SignalChart } from "./SignalChart";
import { ProofPerformanceTable } from "./ProofPerformanceTable";
import { formatCount, formatSeconds } from "./proofPerformance";
import { waveformToSignalPoints } from "./transformers";
import type { ProcessedData, ProofStageBreakdown, VerifiableProofResult } from "./types";

interface MainCSIData {
  processedData: ProcessedData | null;
  csiDataId?: string;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return value != null && isFinite(value) ? value.toFixed(digits) : "—";
}

function formatDuration(seconds: number): string {
  return seconds < 1 ? `${formatNumber(seconds * 1000, 1)} ms` : `${formatNumber(seconds, 3)} 秒`;
}

function proofNormality(proof: VerifiableProofResult | undefined): boolean | undefined {
  return proof?.isNormal;
}

function displayPipelineName(value: string | null | undefined): string {
  if (!value || value.startsWith("5-1")) return "VMD処理";
  return value;
}

function absoluteDifference(left: number | null | undefined, right: number | null | undefined): number | null {
  return left != null && right != null && isFinite(left) && isFinite(right) ? Math.abs(left - right) : null;
}

function csvCell(value: string | number | null | undefined): string {
  if (value == null) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function downloadBenchmarkCsv(
  rows: Array<{ key: string; label: string; proof: VerifiableProofResult }>,
): void {
  const headers = [
    "proof_branch",
    "proof_label",
    "method",
    "circuit_name",
    "proving_system",
    "curve",
    "constraint_count",
    "witness_generation_ms",
    "proof_generation_ms",
    "verification_ms",
    "total_ms",
    "average_proof_time_per_constraint_ns",
    "measured_at",
  ];
  const lines = rows.map(({ key, label, proof }) => {
    const benchmark = proof.benchmark!;
    return [
      key,
      label,
      proof.method,
      benchmark.circuitName,
      benchmark.provingSystem,
      benchmark.curve,
      benchmark.constraintCount,
      benchmark.witnessGenerationMs,
      benchmark.proofGenerationMs,
      benchmark.verificationMs,
      benchmark.totalMs,
      benchmark.averageProofTimePerConstraintNs,
      benchmark.measuredAt,
    ].map(csvCell).join(",");
  });
  const blob = new Blob(["\ufeff", headers.join(","), "\n", lines.join("\n"), "\n"], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "circom_benchmarks.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

function CircomBenchmarkSection({
  proofs,
  csiDataId,
}: {
  proofs: ProcessedData["proofs"];
  csiDataId?: string;
}) {
  const candidates = [
    { key: "python_circom", label: "VMD処理 + Circom", proof: proofs?.python_circom },
    {
      key: "lomb_scargle_circom",
      label: "Lomb–Scargle + Circom",
      proof: proofs?.lomb_scargle_circom,
    },
  ];
  const rows = candidates.filter(
    (row): row is { key: string; label: string; proof: VerifiableProofResult } =>
      row.proof?.benchmark != null,
  );
  if (rows.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
      <div className="flex flex-col gap-3 border-b border-neutral-200 bg-neutral-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-neutral-900">Circom制約・証明時間</h3>
          <p className="mt-1 text-xs text-neutral-500">
            Groth16は全制約を一括証明するため、1制約あたりは証明生成時間の平均値です。
          </p>
        </div>
        {csiDataId ? (
          <a
            href={`${API_BASE}/api/v2/csi-data/${csiDataId}/circom-benchmarks.csv`}
            download
            className="inline-flex h-9 w-fit items-center rounded-lg border border-neutral-300 bg-white px-3 text-xs font-semibold text-neutral-700 hover:bg-neutral-100"
          >
            CSVをダウンロード
          </a>
        ) : (
          <button
            type="button"
            onClick={() => downloadBenchmarkCsv(rows)}
            className="h-9 w-fit rounded-lg border border-neutral-300 bg-white px-3 text-xs font-semibold text-neutral-700 hover:bg-neutral-100"
          >
            CSVをダウンロード
          </button>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-xs">
          <thead className="bg-white text-neutral-500">
            <tr>
              <th className="px-4 py-2 font-medium">回路</th>
              <th className="px-4 py-2 text-right font-medium">制約数</th>
              <th className="px-4 py-2 text-right font-medium">Witness</th>
              <th className="px-4 py-2 text-right font-medium">証明生成</th>
              <th className="px-4 py-2 text-right font-medium">検証</th>
              <th className="px-4 py-2 text-right font-medium">合計</th>
              <th className="px-4 py-2 text-right font-medium">1制約平均</th>
              <th className="px-4 py-2 font-medium">計測日時</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100 text-neutral-700">
            {rows.map(({ key, label, proof }) => {
              const benchmark = proof.benchmark!;
              return (
                <tr key={key}>
                  <td className="px-4 py-3">
                    <p className="font-semibold text-neutral-900">{label}</p>
                    <p className="mt-1 font-mono text-[11px] text-neutral-500">
                      {benchmark.circuitName} / {benchmark.provingSystem} / {benchmark.curve}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {benchmark.constraintCount?.toLocaleString() ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-right font-mono">{formatNumber(benchmark.witnessGenerationMs, 3)} ms</td>
                  <td className="px-4 py-3 text-right font-mono">{formatNumber(benchmark.proofGenerationMs, 3)} ms</td>
                  <td className="px-4 py-3 text-right font-mono">
                    {benchmark.verificationMs == null ? "—" : `${formatNumber(benchmark.verificationMs, 3)} ms`}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-semibold">{formatNumber(benchmark.totalMs, 3)} ms</td>
                  <td className="px-4 py-3 text-right font-mono">
                    {benchmark.averageProofTimePerConstraintNs == null
                      ? "—"
                      : `${formatNumber(benchmark.averageProofTimePerConstraintNs, 3)} ns`}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    {new Date(benchmark.measuredAt).toLocaleString("ja-JP")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {rows.map(({ key, label, proof }) =>
        proof.benchmark?.stageBreakdown ? (
          <StageBreakdownTable
            key={`${key}-stages`}
            label={label}
            proofGenerationMs={proof.benchmark.proofGenerationMs}
            breakdown={proof.benchmark.stageBreakdown}
          />
        ) : null,
      )}
    </div>
  );
}

function AlgorithmDifferenceSection({ isApproxVmd }: { isApproxVmd: boolean }) {
  const sharedStages = ["CSI振幅", "SNR選択", "帯域抽出", "PCA"];

  return (
    <section className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
      <div className="border-b border-neutral-200 bg-neutral-50 px-4 py-3">
        <h3 className="text-sm font-semibold text-neutral-900">2つの呼吸推定処理の違い</h3>
        <p className="mt-1 text-xs leading-relaxed text-neutral-500">
          PCAまでは同じデータを使用し、その後の周波数推定とCircomで証明する計算が異なります。
        </p>
      </div>

      <div className="px-4 py-4">
        <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-600">
          <span className="font-semibold text-neutral-800">共通前処理</span>
          {sharedStages.map((stage, index) => (
            <div key={stage} className="flex items-center gap-2">
              {index > 0 && <span aria-hidden="true" className="text-neutral-300">→</span>}
              <span className="rounded-md border border-neutral-200 bg-neutral-50 px-2.5 py-1.5">
                {stage}
              </span>
            </div>
          ))}
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <article className="rounded-lg border border-teal-200 bg-teal-50/60 p-4">
            <div className="flex items-center justify-between gap-3">
              <h4 className="text-sm font-semibold text-teal-950">VMD処理</h4>
              <span className="rounded-full bg-teal-100 px-2.5 py-1 text-[11px] font-semibold text-teal-800">
                モード分解
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-teal-950/75">
              {isApproxVmd
                ? "PythonはPCA波形を5つのVMDモードへ分解し、各モードのFFTピークから呼吸成分とBPMを選びます。Circom近似VMDは入力波形をDFTし、3つのスペクトルモードを4回の反復で更新してピークを選びます。"
                : "選択したPCA波形を5つのVMDモードへ分解し、各モードのFFTピークから呼吸成分とBPMを選びます。Circomは供給されたVMD入力と選択結果を検証します。"}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-teal-900">
              <span className="rounded bg-white/80 px-2 py-1">PCA波形</span>
              <span aria-hidden="true">→</span>
              <span className="rounded bg-white/80 px-2 py-1">
                {isApproxVmd ? "Python VMD 5モード / Circom近似 3モード" : "VMD 5モード"}
              </span>
              <span aria-hidden="true">→</span>
              <span className="rounded bg-white/80 px-2 py-1">FFTピーク</span>
            </div>
            <dl className="mt-4 border-t border-teal-200 pt-3 text-xs">
              <div className="grid grid-cols-[5.5rem_1fr] gap-2">
                <dt className="font-semibold text-teal-900">時刻の扱い</dt>
                <dd className="text-teal-950/75">
                  {isApproxVmd
                    ? "Python VMDは既存の100 Hz前提。Circom近似VMDは128サンプル・2 Hz（64秒）で処理"
                    : "Python VMDは既存の100 Hz前提。Circomには縮約したVMD入力を渡します"}
                </dd>
              </div>
              <div className="mt-2 grid grid-cols-[5.5rem_1fr] gap-2">
                <dt className="font-semibold text-teal-900">Circom検証</dt>
                <dd className="text-teal-950/75">
                  {isApproxVmd
                    ? "PCA波形をDFTし、3つのスペクトルモードを4回更新して適応中心を求め、ピークと正常BPM帯域を回路内で検証"
                    : "秘密のVMD入力・5モード・選択フラグから、再構成、狭帯域性、DFTピーク、正常BPM帯域を検証"}
                </dd>
              </div>
            </dl>
          </article>

          <article className="rounded-lg border border-blue-200 bg-blue-50/60 p-4">
            <div className="flex items-center justify-between gap-3">
              <h4 className="text-sm font-semibold text-blue-950">Lomb–Scargle処理</h4>
              <span className="rounded-full bg-blue-100 px-2.5 py-1 text-[11px] font-semibold text-blue-800">
                不均一時刻を直接解析
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-blue-950/75">
              VMDへ分解せず、PCA波形と実測タイムスタンプからLomb–Scargleスコアを求め、PCとBPMを選びます。
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-blue-900">
              <span className="rounded bg-white/80 px-2 py-1">PCA波形＋時刻</span>
              <span aria-hidden="true">→</span>
              <span className="rounded bg-white/80 px-2 py-1">LSスコア</span>
              <span aria-hidden="true">→</span>
              <span className="rounded bg-white/80 px-2 py-1">全帯域ピーク</span>
            </div>
            <dl className="mt-4 border-t border-blue-200 pt-3 text-xs">
              <div className="grid grid-cols-[5.5rem_1fr] gap-2">
                <dt className="font-semibold text-blue-900">時刻の扱い</dt>
                <dd className="text-blue-950/75">パケットごとの不均一な実測時刻を使用</dd>
              </div>
              <div className="mt-2 grid grid-cols-[5.5rem_1fr] gap-2">
                <dt className="font-semibold text-blue-900">Circom検証</dt>
                <dd className="text-blue-950/75">
                  秘密のPCA波形と公開時刻から三角関数を近似し、LSスコア、PC選択、ピーク、正常BPM帯域まで回路内で計算
                </dd>
              </div>
            </dl>
          </article>
        </div>
      </div>
    </section>
  );
}

function LombScargleTimingSection({ analysis }: { analysis: ProcessedData["analysis"] }) {
  const lomb = analysis?.lomb_scargle;
  const steps = lomb?.processing_steps ?? [];
  if (steps.length === 0) return null;

  const total = lomb?.processing_time_seconds ?? steps.reduce((sum, step) => sum + step.seconds, 0);

  return (
    <section className="overflow-hidden rounded-lg border border-blue-200 bg-white">
      <div className="flex flex-col gap-1 border-b border-blue-100 bg-blue-50/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-blue-950">Lomb–Scargle処理時間</h3>
          <p className="mt-1 text-xs text-blue-900/65">
            共通PCA出力を受け取った後の実測値です。CircomのWitness・証明・検証時間は下部に分けて表示します。
          </p>
        </div>
        <p className="mt-1 shrink-0 font-mono text-sm font-semibold text-blue-950 sm:mt-0">
          合計 {formatDuration(total)}
        </p>
      </div>
      <div className="overflow-x-auto px-4 py-2">
        <table className="w-full min-w-[480px] text-left text-xs">
          <thead className="text-neutral-500">
            <tr>
              <th className="py-2 pr-4 font-medium">処理</th>
              <th className="py-2 pr-4 text-right font-medium">所要時間</th>
              <th className="py-2 text-right font-medium">全体比</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100 text-neutral-700">
            {steps.map((step) => (
              <tr key={step.key}>
                <td className="py-2.5 pr-4 font-medium text-neutral-900">{step.label}</td>
                <td className="py-2.5 pr-4 text-right font-mono">{formatDuration(step.seconds)}</td>
                <td className="py-2.5 text-right font-mono">
                  {total > 0 ? `${formatNumber((step.seconds / total) * 100, 1)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StageBreakdownTable({
  label,
  proofGenerationMs,
  breakdown,
}: {
  label: string;
  proofGenerationMs: number;
  breakdown: ProofStageBreakdown;
}) {
  return (
    <div className="border-t border-neutral-200 px-4 py-4">
      <h4 className="text-sm font-semibold text-neutral-900">
        {label} — 処理段階別の証明生成時間
      </h4>
      <p className="mt-1 text-xs text-neutral-500">
        証明生成 {formatNumber(proofGenerationMs, 1)} ms の内訳。Groth16は全制約を一括で証明するため
        段階ごとの直接計測はできず、段階別回路で実測したプロファイルの制約数比で按分している。
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-xs">
          <thead className="text-neutral-500">
            <tr>
              <th className="py-2 pr-4 font-medium">段階</th>
              <th className="py-2 pr-4 text-right font-medium">制約数</th>
              <th className="py-2 pr-4 text-right font-medium">割合</th>
              <th className="py-2 text-right font-medium">推定時間</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100 text-neutral-700">
            {breakdown.stages.map((stage) => (
              <tr key={stage.key}>
                <td className="py-2 pr-4">
                  <p className="font-medium text-neutral-900">{stage.label}</p>
                  {stage.description ? (
                    <p className="mt-0.5 text-[11px] text-neutral-500">{stage.description}</p>
                  ) : null}
                </td>
                <td className="py-2 pr-4 text-right font-mono">
                  {stage.constraints.toLocaleString()}
                </td>
                <td className="py-2 pr-4 text-right font-mono">
                  {formatNumber(stage.constraintShare * 100, 1)}%
                </td>
                <td className="py-2 text-right font-mono">
                  {formatNumber(stage.estimatedMs, 1)} ms
                </td>
              </tr>
            ))}
            <tr className="text-neutral-500">
              <td className="py-2 pr-4">
                <p className="font-medium">固定オーバーヘッド</p>
                <p className="mt-0.5 text-[11px]">snarkjsプロセス起動とzkey読み込み（制約数に依存しない）</p>
              </td>
              <td className="py-2 pr-4 text-right font-mono">—</td>
              <td className="py-2 pr-4 text-right font-mono">—</td>
              <td className="py-2 text-right font-mono">
                {formatNumber(breakdown.fixedOverheadMs, 1)} ms
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
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
  const valid = completed && proof.isValid === true;
  const normal = proofNormality(proof);

  return (
    <article className="rounded-lg border border-neutral-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-neutral-900">{title}</h3>
          <p className="mt-1 font-mono text-xs text-neutral-500">
            {displayPipelineName(
              proof?.method ?? fallbackMethod,
            )}
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
                : "未実行"}
        </span>
      </div>

      {completed && (
        <div className="mt-4 space-y-2 border-t border-neutral-100 pt-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-neutral-500">回路内の呼吸判定</span>
            <span className={`text-sm font-semibold ${normal ? "text-emerald-700" : "text-amber-700"}`}>
              {normal == null ? "判定なし" : normal ? "正常帯域" : "正常帯域外"}
            </span>
          </div>
          {proof.estimatedBpm != null && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-500">
                {proof.method === "vmd_approx_fixed_point"
                  ? "回路内近似VMD推定"
                  : proof.method === "lomb_scargle_timestamp_trig_fixed_point"
                    ? "回路内Lomb–Scargle推定"
                    : "回路内推定"}
              </span>
              <span className="font-mono text-sm font-semibold text-neutral-800">
                {formatNumber(proof.estimatedBpm, 2)} BPM
              </span>
            </div>
          )}
          {proof.proofScope && (
            <p className="break-words font-mono text-[10px] leading-relaxed text-neutral-400">
              {proof.proofScope}
            </p>
          )}
        </div>
      )}

      {completed && proof.performance && (
        <dl className="mt-3 grid grid-cols-2 gap-3 border-t border-neutral-100 pt-3">
          <div>
            <dt className="text-xs text-neutral-500">制約数</dt>
            <dd className="mt-0.5 text-sm font-semibold tabular-nums text-neutral-900">
              {formatCount(proof.performance.constraint_count)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-neutral-500">証明生成時間</dt>
            <dd className="mt-0.5 text-sm font-semibold tabular-nums text-neutral-900">
              {formatSeconds(proof.performance.generation_time_seconds)}
            </dd>
          </div>
        </dl>
      )}

      {proof?.status === "failed" && (
        <p className="mt-3 break-words rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
          {proof.error ?? proof.error_type ?? "証明生成に失敗しました"}
        </p>
      )}
    </article>
  );
}

function MainPanel({ processedData, csiDataId }: MainCSIData) {
  if (!processedData) return null;

  if (processedData.error) {
    return <p className="text-sm text-red-600">{processedData.error}</p>;
  }

  if (processedData.analysis) {
    const analysis = processedData.analysis;
    const circom = processedData.proofs?.python_circom;
    const lombCircom = processedData.proofs?.lomb_scargle_circom;
    const isApproxVmd = circom?.method === "vmd_approx_fixed_point";
    const lomb = analysis.lomb_scargle;
    const bpmEvaluation = processedData.bpm_evaluation;
    const waveformPoints = waveformToSignalPoints(analysis.respiration_waveform);
    const diagnostics = analysis.certificate_diagnostics;
    const proofPerformanceEntries = [
      { label: "VMD処理 + Circom", proof: circom },
      { label: "Lomb–Scargle + Circom", proof: lombCircom },
    ];
    const hasProofPerformance = proofPerformanceEntries.some((entry) => entry.proof?.performance);
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

        <AlgorithmDifferenceSection isApproxVmd={isApproxVmd} />

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
            <MetricCard label="Python VMD" value={analysis.breathing_rate_bpm ?? null} unit="BPM" />
            <MetricCard
              label="Circom近似VMD"
              value={circom?.method === "vmd_approx_fixed_point" ? circom.estimatedBpm ?? null : null}
              unit="BPM"
            />
            <MetricCard
              label="Python Lomb–Scargle"
              value={lomb?.breathing_rate_bpm ?? null}
              unit="BPM"
            />
            <MetricCard
              label="Circom Lomb–Scargle"
              value={lombCircom?.estimatedBpm ?? null}
              unit="BPM"
            />
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <MetricCard
              label="VMD Python–Circom差"
              value={absoluteDifference(analysis.breathing_rate_bpm, circom?.method === "vmd_approx_fixed_point" ? circom.estimatedBpm : null)}
              unit="BPM"
            />
            <MetricCard
              label="Lomb–Scargle Python–Circom差"
              value={absoluteDifference(lomb?.breathing_rate_bpm, lombCircom?.estimatedBpm)}
              unit="BPM"
            />
            <MetricCard
              label="VMD処理とLomb–Scargleの推定差"
              value={analysis.algorithm_comparison?.absolute_difference_bpm ?? null}
              unit="BPM"
            />
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

        <LombScargleTimingSection analysis={analysis} />

        <SignalChart title="VMDで抽出した呼吸波形" points={waveformPoints} color="#0f766e" />

        <div>
          <h3 className="mb-3 text-sm font-semibold text-neutral-900">証明</h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <ProofCard
              title={isApproxVmd ? "近似VMD + Circom" : "VMD証明書検証"}
              proof={circom}
              fallbackMethod="breathing_certificate"
            />
            <ProofCard
              title="Lomb–Scargle + Circom"
              proof={lombCircom}
              fallbackMethod="lomb_scargle_timestamp_trig_fixed_point"
            />
          </div>
        </div>

        {hasProofPerformance && (
          <div>
            <h3 className="mb-3 text-sm font-semibold text-neutral-900">制約数と証明生成時間</h3>
            <ProofPerformanceTable entries={proofPerformanceEntries} />
          </div>
        )}

        <CircomBenchmarkSection proofs={processedData.proofs} csiDataId={csiDataId} />

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

        {diagnostics && circom?.method !== "vmd_approx_fixed_point" && (
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
          <p>解析パイプライン: {displayPipelineName(analysis.pipeline)}</p>
          <p className="mt-2">
            一時無効: {(processedData.disabled_methods ?? []).join(", ") || "なし"}
          </p>
        </div>
      </div>
    );
  }

  return <p className="text-sm text-neutral-500">解析結果がまだありません。</p>;
}

export function AnalysisResultPanel(props: MainCSIData) {
  return <MainPanel {...props} />;
}
