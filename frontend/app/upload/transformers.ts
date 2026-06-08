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
  const methods = data?.breathing_rate_comparison?.methods ?? {};
  return {
    fft: methods["fft"] ?? null,
    wavelet: methods["wavelet"] ?? null,
    music: methods["music"] ?? null,
    final: data?.breathing_rate_comparison?.final_bpm ?? null,
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
