import { parseBundle, type ProofBundle } from "./types";
import type { VerifiableProofResult } from "../upload/types";

const METHODS: Record<string, string> = {
  breathing_certificate: "csi_breathing_certificate",
  breathing_certificate_committed: "csi_breathing_certificate_committed",
  preprocess_projection: "csi_preprocess_projection",
  vmd_approx_fixed_point: "csi_vmd_approx",
  lomb_scargle_timestamp_trig_fixed_point: "csi_lomb_scargle_normality",
};
const PREFIX = "csi-proof-handoff:";
const MAX_AGE = 10 * 60 * 1000;

export function analysisProofBundle(
  result: VerifiableProofResult,
): ProofBundle {
  if (result.status !== "completed" || result.isValid !== true)
    throw new Error("有効な証明の生成が完了していません。");
  if (!result.proof || !result.publicSignals)
    throw new Error("この解析結果に証明本体がありません。再解析が必要です。");
  const circuit = METHODS[result.method || ""];
  if (!circuit) throw new Error("この解析方式の回路を識別できません。");
  // Explicit allowlist: never transfer waveforms, diagnostics, device IDs or tokens.
  return parseBundle(
    { circuit, proof: result.proof, publicSignals: result.publicSignals },
    circuit,
  );
}

export function storeProofHandoff(bundle: ProofBundle): string {
  for (let index = sessionStorage.length - 1; index >= 0; index--) {
    const key = sessionStorage.key(index);
    if (key?.startsWith(PREFIX)) sessionStorage.removeItem(key);
  }
  const id = crypto.randomUUID();
  sessionStorage.setItem(
    PREFIX + id,
    JSON.stringify({
      createdAt: Date.now(),
      bundle: parseBundle(bundle, bundle.circuit),
    }),
  );
  return id;
}

export function consumeProofHandoff(id: string): ProofBundle {
  if (!/^[0-9a-f-]{36}$/i.test(id))
    throw new Error("証明の受け渡しIDが不正です。");
  const key = PREFIX + id;
  const value = sessionStorage.getItem(key);
  sessionStorage.removeItem(key);
  if (!value)
    throw new Error(
      "解析結果の証明が見つかりません。元の画面からもう一度開いてください。",
    );
  const parsed = JSON.parse(value);
  if (
    typeof parsed.createdAt !== "number" ||
    Date.now() - parsed.createdAt > MAX_AGE ||
    parsed.createdAt > Date.now()
  )
    throw new Error(
      "証明の受け渡しが期限切れです。元の画面からもう一度開いてください。",
    );
  return parseBundle(parsed.bundle, "");
}
