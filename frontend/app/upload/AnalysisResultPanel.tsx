import { MetricCard } from "./MetricCard";
import { SpectrumChart } from "./SpectrumChart";
import { dataframeToSpectrumPoints, pickBreathingBpm, pickSimilarityScores } from "./transformers";
import type { DataframeDict, ProcessedData } from "./types";

interface BaseCSIData {
  mode: "base";
  fft_dataframe: DataframeDict;
  wavelet_dataframe: DataframeDict;
  music_dataframe: DataframeDict;
}

interface MainCSIData {
  mode: "main";
  processedData: ProcessedData | null;
}

type Props = BaseCSIData | MainCSIData;

function BasePanel({ fft_dataframe, wavelet_dataframe, music_dataframe }: BaseCSIData) {
  const fftPoints = dataframeToSpectrumPoints(fft_dataframe);
  const waveletPoints = dataframeToSpectrumPoints(wavelet_dataframe);
  const musicPoints = dataframeToSpectrumPoints(music_dataframe);

  return (
    <div className="space-y-3">
      <SpectrumChart title="FFT スペクトル" points={fftPoints} />
      <SpectrumChart title="Wavelet スペクトル" points={waveletPoints} />
      <SpectrumChart title="MUSIC スペクトル" points={musicPoints} />
    </div>
  );
}

function MainPanel({ processedData }: MainCSIData) {
  if (!processedData) return null;

  if (processedData.error) {
    return <p className="text-sm text-red-600">{processedData.error}</p>;
  }

  const bpm = pickBreathingBpm(processedData);
  const similarity = pickSimilarityScores(processedData);
  const comparison = processedData.base_csi_comparison;
  const primaryMethod = comparison?.primary_method ?? comparison?.comparison_summary?.primary_method;
  const dimensions = comparison?.data_dimensions;

  const fftPoints = dataframeToSpectrumPoints(processedData.fft_dataframe ?? null);
  const waveletPoints = dataframeToSpectrumPoints(processedData.wavelet_dataframe ?? null);
  const musicPoints = dataframeToSpectrumPoints(processedData.music_dataframe ?? null);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard label="呼吸数 (合意)" value={bpm.final} unit="BPM" />
        <MetricCard label="FFT BPM" value={bpm.fft} unit="BPM" />
        <MetricCard label="Wavelet BPM" value={bpm.wavelet} unit="BPM" />
        <MetricCard label="MUSIC BPM" value={bpm.music} unit="BPM" />
      </div>

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

      {(processedData.wavelet_zkp || processedData.music_zkp || processedData.blockchain_proof_id) && (
        <div className="rounded-lg border border-neutral-200 bg-white p-4">
          <p className="text-sm font-semibold text-neutral-800">ZKP / ブロックチェーン記録</p>
          <div className="mt-3 grid gap-3 text-xs text-neutral-600 sm:grid-cols-3">
            <div className="rounded-lg bg-neutral-50 p-3">
              <p className="text-neutral-500">FFT Proof ID</p>
              <p className="mt-1 break-all font-mono text-neutral-900">
                {processedData.blockchain_proof_id ?? "—"}
              </p>
            </div>
            <div className="rounded-lg bg-neutral-50 p-3">
              <p className="text-neutral-500">Wavelet</p>
              <p className="mt-1 font-semibold text-neutral-900">
                {processedData.wavelet_zkp
                  ? processedData.wavelet_zkp.is_normal
                    ? "normal"
                    : "abnormal"
                  : "—"}
              </p>
              <p className="mt-1 break-all font-mono">
                {processedData.wavelet_zkp?.proof_id ?? ""}
              </p>
            </div>
            <div className="rounded-lg bg-neutral-50 p-3">
              <p className="text-neutral-500">MUSIC</p>
              <p className="mt-1 font-semibold text-neutral-900">
                {processedData.music_zkp
                  ? processedData.music_zkp.is_normal
                    ? "normal"
                    : "abnormal"
                  : "—"}
              </p>
              <p className="mt-1 break-all font-mono">
                {processedData.music_zkp?.proof_id ?? ""}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-3">
        <SpectrumChart title="FFT スペクトル" points={fftPoints} />
        <SpectrumChart title="Wavelet スペクトル" points={waveletPoints} />
        <SpectrumChart title="MUSIC スペクトル" points={musicPoints} />
      </div>
    </div>
  );
}

export function AnalysisResultPanel(props: Props) {
  if (props.mode === "base") return <BasePanel {...props} />;
  return <MainPanel {...props} />;
}
