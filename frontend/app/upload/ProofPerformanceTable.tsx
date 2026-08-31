import {
  NOT_AVAILABLE,
  formatCount,
  formatSeconds,
  formatTimePerConstraint,
  selectMeasuredProofs,
  type ProofPerformanceEntry,
} from "./proofPerformance";

interface Props {
  entries: ProofPerformanceEntry[];
}

const COLUMNS = [
  "証明",
  "回路",
  "制約数",
  "witness生成",
  "prove",
  "生成合計",
  "1制約あたり",
  "ローカル検証",
] as const;

export function ProofPerformanceTable({ entries }: Props) {
  const measured = selectMeasuredProofs(entries);

  if (measured.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[44rem] border-collapse text-sm">
        <thead>
          <tr className="border-y border-neutral-200 bg-neutral-50 text-left text-xs text-neutral-500">
            {COLUMNS.map((column) => (
              <th key={column} scope="col" className="px-3 py-2 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {measured.map(({ label, performance }) => (
            <tr key={label} className="border-b border-neutral-100">
              <th scope="row" className="px-3 py-2 text-left font-semibold text-neutral-900">
                {label}
              </th>
              <td className="px-3 py-2 font-mono text-xs text-neutral-500">
                {performance.circuit_name ?? performance.proof_system ?? NOT_AVAILABLE}
              </td>
              <td className="px-3 py-2 tabular-nums text-neutral-900">
                {formatCount(performance.constraint_count)}
              </td>
              <td className="px-3 py-2 tabular-nums text-neutral-600">
                {formatSeconds(performance.witness_time_seconds)}
              </td>
              <td className="px-3 py-2 tabular-nums text-neutral-600">
                {formatSeconds(performance.prove_time_seconds)}
              </td>
              <td className="px-3 py-2 font-semibold tabular-nums text-neutral-900">
                {formatSeconds(performance.generation_time_seconds)}
              </td>
              <td className="px-3 py-2 tabular-nums text-neutral-600">
                {formatTimePerConstraint(performance)}
              </td>
              <td className="px-3 py-2 tabular-nums text-neutral-600">
                {formatSeconds(performance.verify_time_seconds)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-neutral-500">
        生成合計 = witness生成 + prove。各証明は並列実行されるため、合計は解析全体の所要時間とは一致しません。
      </p>
    </div>
  );
}
