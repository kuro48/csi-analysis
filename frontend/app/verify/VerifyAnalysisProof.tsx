"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { VerifiableProofResult } from "../upload/types";
import { analysisProofBundle, storeProofHandoff } from "./handoff";

export function VerifyAnalysisProof({
  result,
}: {
  result: VerifiableProofResult;
}) {
  const router = useRouter();
  const [error, setError] = useState("");
  let unavailable = "";
  try {
    analysisProofBundle(result);
  } catch (failure) {
    unavailable = (failure as Error).message;
  }
  return (
    <div className="mt-4 border-t border-neutral-100 pt-3">
      <button
        type="button"
        disabled={!!unavailable}
        className="w-full rounded-lg bg-teal-700 px-3 py-2 text-xs font-semibold text-white hover:bg-teal-800 disabled:bg-neutral-200 disabled:text-neutral-500"
        onClick={() => {
          try {
            const id = storeProofHandoff(analysisProofBundle(result));
            router.push(`/verify?import=${id}`);
          } catch {
            setError(
              "証明を引き継げませんでした。ブラウザの保存設定を確認してください。",
            );
          }
        }}
      >
        この証明をオンチェーンで検証 →
      </button>
      <p className="mt-2 text-xs leading-relaxed text-neutral-500">
        {unavailable ||
          "生成済み証明と公開入力を引き継ぎます。送信前に対応回路と公開内容を確認します。"}
      </p>
      {error && (
        <p role="alert" className="mt-2 text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
