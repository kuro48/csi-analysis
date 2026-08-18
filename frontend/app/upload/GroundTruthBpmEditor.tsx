"use client";

import { useState } from "react";
import { updateGroundTruthBpm } from "./api";
import { GroundTruthBpmInput, parseGroundTruthBpm } from "./GroundTruthBpmInput";
import type { MainCSIResponse } from "./types";

interface GroundTruthBpmEditorProps {
  recordId: string;
  groundTruthBpm?: number | null;
  onSaved: (record: MainCSIResponse) => void;
}

export function GroundTruthBpmEditor({ recordId, groundTruthBpm, onSaved }: GroundTruthBpmEditorProps) {
  const [input, setInput] = useState(groundTruthBpm != null ? String(groundTruthBpm) : "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async (value: number | null) => {
    setSaving(true);
    setError(null);
    try {
      onSaved(await updateGroundTruthBpm(recordId, value));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "正解BPMの保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    try {
      const value = parseGroundTruthBpm(input);
      if (value === null) {
        setError("正解BPMを入力してください。削除する場合は削除ボタンを使用してください");
        return;
      }
      await save(value);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "正解BPMを確認してください");
    }
  };

  return (
    <div className="rounded-lg border border-teal-100 bg-teal-50/60 p-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <GroundTruthBpmInput
          value={input}
          onChange={(value) => {
            setInput(value);
            setError(null);
          }}
          disabled={saving}
        />
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="h-10 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white transition-colors hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? "保存中..." : "正解BPMを保存"}
        </button>
        {groundTruthBpm != null && (
          <button
            type="button"
            onClick={() => save(null)}
            disabled={saving}
            className="h-10 rounded-lg border border-neutral-300 bg-white px-4 text-sm font-semibold text-neutral-700 transition-colors hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            削除
          </button>
        )}
      </div>
      <p className="mt-2 text-xs text-neutral-600">
        アップロード後に入力できます。保存すると計測BPMとの差分が評価データへ追加されます。
      </p>
      {error && <p className="mt-2 text-xs font-medium text-red-700">{error}</p>}
    </div>
  );
}
