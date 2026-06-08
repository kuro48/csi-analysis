interface Props {
  label: string;
  value: number | null | undefined;
  unit?: string;
  digits?: number;
}

export function MetricCard({ label, value, unit = "", digits = 1 }: Props) {
  const display = value != null && isFinite(value) ? value.toFixed(digits) : "—";
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
      <p className="text-xs text-neutral-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-neutral-900">
        {display}
        {value != null && unit && (
          <span className="ml-1 text-sm font-normal text-neutral-500">{unit}</span>
        )}
      </p>
    </div>
  );
}
