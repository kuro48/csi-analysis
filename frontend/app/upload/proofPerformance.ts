import type { ProofPerformance, VerifiableProofResult } from "./types";

export const NOT_AVAILABLE = "—";
const MILLISECOND_THRESHOLD_SECONDS = 1;
const MICROSECONDS_PER_SECOND = 1_000_000;

export interface ProofPerformanceEntry {
  label: string;
  proof: VerifiableProofResult | undefined;
}

export interface MeasuredProof {
  label: string;
  performance: ProofPerformance;
}

export function formatSeconds(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return NOT_AVAILABLE;
  return value < MILLISECOND_THRESHOLD_SECONDS
    ? `${(value * 1000).toFixed(0)} ms`
    : `${value.toFixed(2)} s`;
}

export function formatCount(value: number | null | undefined): string {
  return value != null && isFinite(value) ? value.toLocaleString() : NOT_AVAILABLE;
}

/** 制約1本あたりの証明生成時間。回路規模と生成時間の関係を見るための指標。 */
export function formatTimePerConstraint(performance: ProofPerformance): string {
  const { generation_time_seconds: seconds, constraint_count: constraints } = performance;
  if (seconds == null || !isFinite(seconds)) return NOT_AVAILABLE;
  if (constraints == null || !isFinite(constraints) || constraints <= 0) return NOT_AVAILABLE;
  return `${((seconds * MICROSECONDS_PER_SECOND) / constraints).toFixed(2)} µs`;
}

/** 計測値を持つ証明だけを表示対象として取り出す。 */
export function selectMeasuredProofs(entries: ProofPerformanceEntry[]): MeasuredProof[] {
  return entries.flatMap(({ label, proof }) =>
    proof?.performance ? [{ label, performance: proof.performance }] : [],
  );
}
