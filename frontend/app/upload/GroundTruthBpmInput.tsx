interface GroundTruthBpmInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function parseGroundTruthBpm(value: string): number | null {
  if (value.trim() === "") return null;
  const bpm = Number(value);
  if (!Number.isFinite(bpm) || bpm <= 0 || bpm > 120) {
    throw new Error("正解BPMは0より大きく120以下で入力してください");
  }
  return bpm;
}

export function GroundTruthBpmInput({ value, onChange, disabled = false }: GroundTruthBpmInputProps) {
  return (
    <label className="block sm:w-44">
      <span className="mb-1 block text-xs font-semibold text-neutral-700">正解BPM（任意）</span>
      <div className="relative">
        <input
          type="number"
          inputMode="decimal"
          min="0.1"
          max="120"
          step="0.1"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          placeholder="例: 15"
          className="h-10 w-full rounded-lg border border-neutral-300 bg-white px-3 pr-12 text-sm text-neutral-900 outline-none transition-colors placeholder:text-neutral-400 focus:border-teal-600 focus:ring-2 focus:ring-teal-100 disabled:bg-neutral-100"
        />
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-neutral-500">
          BPM
        </span>
      </div>
    </label>
  );
}
