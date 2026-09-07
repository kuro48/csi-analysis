import type { SignalPoint } from "./types";

export const BREATHING_PIPELINE_FS = 100;
const MAX_SIGNAL_POINTS = 2000;

export function waveformToSignalPoints(
  waveform: number[] | null | undefined,
  sampleRate = BREATHING_PIPELINE_FS,
): SignalPoint[] {
  if (!waveform?.length || sampleRate <= 0) return [];

  const step = Math.max(1, Math.ceil(waveform.length / MAX_SIGNAL_POINTS));
  const points: SignalPoint[] = [];
  for (let index = 0; index < waveform.length; index += step) {
    const amplitude = waveform[index];
    if (typeof amplitude !== "number" || !isFinite(amplitude)) continue;
    points.push({ time: index / sampleRate, amplitude });
  }
  return points;
}
