import type { DataframeDict, ProcessedData, SignalDict, SignalPoint, SpectrumPoint } from "./types";

export function signalDictToPoints(signal: SignalDict): SignalPoint[] {
  if (!signal?.time || !signal?.amplitude_avg) return [];

  const timeMap = signal.time;
  const ampMap = signal.amplitude_avg;
  const startMs = signal.start_timestamp ? new Date(signal.start_timestamp).getTime() : null;

  const points: SignalPoint[] = [];
  for (const key of Object.keys(timeMap)) {
    const time = timeMap[key];
    const amp = ampMap[key];
    if (time == null || amp == null || !isFinite(time) || !isFinite(amp)) continue;
    const ts = startMs != null ? startMs + time * 1000 : undefined;
    points.push({ time, ts, amplitude: amp });
  }

  return points.sort((a, b) => a.time - b.time);
}

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

export type SignalSource = "amplitude" | "phase";

export function pickBreathingBpm(
  data: ProcessedData | null,
  source: SignalSource = "amplitude",
): {
  fft: number | null;
  wavelet: number | null;
  music: number | null;
} {
  const comparison =
    source === "phase"
      ? data?.breathing_rate_phase_comparison
      : data?.breathing_rate_comparison;

  return {
    fft: comparison?.fft_bpm ?? null,
    wavelet: comparison?.wavelet_bpm ?? null,
    music: comparison?.music_bpm ?? null,
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
