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
