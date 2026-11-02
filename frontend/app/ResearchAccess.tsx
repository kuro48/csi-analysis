"use client";

import { useState } from "react";
import { setOperatorToken, useOperatorToken } from "./operator-access";

export function ResearchAccess() {
  const token = useOperatorToken();
  const [draft, setDraft] = useState("");
  return (
    <details className="rounded-lg border border-neutral-200 bg-white p-4 text-sm">
      <summary className="cursor-pointer font-semibold text-neutral-700">
        解析APIへのアクセス{" "}
        {token ? "（トークン設定済み）" : "（認証が必要な環境で設定）"}
      </summary>
      <form
        className="mt-3 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setOperatorToken(draft);
          setDraft("");
        }}
      >
        <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-neutral-600">
          運用者アクセストークン
          <input
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="rounded border border-neutral-300 px-3 py-2"
          />
        </label>
        <button
          type="submit"
          disabled={!draft.trim()}
          className="rounded bg-teal-700 px-4 py-2 text-xs text-white disabled:opacity-40"
        >
          適用
        </button>
        {token && (
          <button
            type="button"
            onClick={() => setOperatorToken("")}
            className="rounded border px-4 py-2 text-xs"
          >
            解除
          </button>
        )}
      </form>
      <p className="mt-2 text-xs text-neutral-500">
        トークンはページ間で共有し、このタブのメモリ内だけで保持します。再読み込みすると解除されます。
      </p>
    </details>
  );
}
