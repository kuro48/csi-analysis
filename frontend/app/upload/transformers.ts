import type { DataframeDict, ProcessedData, SpectrumPoint } from "./types";

export function dataframeToSpectrumPoints(df: DataframeDict): SpectrumPoint[] {
  if (!df?.frequency || !df?.magnitude_avg) return [];

  const freqMap = df.frequency;
  const magMap = df.magnitude_avg;

  const points: SpectrumPoint[] = [];
  for (const key of Object.keys(freqMap)) {
    const freq = freqMap[key];
    const mag = magMap[key];
    if (freq == null || mag == null || !isFinite(freq) || !isFinite(mag)) continue;
    points.push({ frequency: freq, magnitude: mag });
  }

  return points.sort((a, b) => a.frequency - b.frequency);
}

export function pickBreathingBpm(data: ProcessedData | null): {
  fft: number | null;
  wavelet: number | null;
  music: number | null;
  final: number | null;
} {
  const comparison = data?.breathing_rate_comparison;
  const methods = comparison?.methods ?? {};
  const fft = methods["fft"] ?? methods["fft_bpm"] ?? comparison?.fft_bpm ?? null;
  const wavelet = methods["wavelet"] ?? methods["wavelet_bpm"] ?? comparison?.wavelet_bpm ?? null;
  const music = methods["music"] ?? methods["music_bpm"] ?? comparison?.music_bpm ?? null;
  const preferredMethod = comparison?.preferred_method;
  const preferred = preferredMethod === "fft"
    ? fft
    : preferredMethod === "wavelet"
      ? wavelet
      : preferredMethod === "music"
        ? music
        : null;

  return {
    fft,
    wavelet,
    music,
    final: comparison?.final_bpm ?? preferred,
  };
}

export function pickSimilarityScores(
  data: ProcessedData | null
): Partial<Record<"fft" | "wavelet" | "music", number>> {
  const comparison = data?.base_csi_comparison;
  if (!comparison) return {};

  const result: Partial<Record<"fft" | "wavelet" | "music", number>> = {};
  for (const method of ["fft", "wavelet", "music"] as const) {
    const m = comparison.methods[method];
    if (m != null) result[method] = m.similarity_score;
  }
  return result;
}
