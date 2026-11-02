export type Circuit = {
  name: string;
  circuitId: string;
  address: string;
  publicSignalCount: number;
  verificationKeyHash: string;
};
export type ChainStatus = {
  connected: boolean;
  message?: string;
  chainId?: number;
  networkName?: string;
  registryAddress?: string;
  explorerUrl?: string;
  currentBlock?: number;
  totalVerified?: number;
  confirmationsRequired?: number;
  circuits: Circuit[];
};
export type ProofBundle = {
  circuit: string;
  proof: {
    protocol: string;
    curve: string;
    pi_a: string[];
    pi_b: string[][];
    pi_c: string[];
  };
  publicSignals: string[];
};
export type Receipt = {
  status: "pending" | "confirming" | "confirmed" | "reverted" | "not_found";
  transactionHash?: string;
  proofId?: string;
  blockNumber?: number;
  confirmations: number;
  gasUsed?: number;
  statementHash?: string;
  submitter?: string;
};
export type Prepared = {
  alreadyVerified: boolean;
  proofId: string;
  chainId: number;
  to: string;
  data: string;
  value: string;
  record?: Receipt;
};

export function parseBundle(
  value: unknown,
  defaultCircuit: string,
): ProofBundle {
  if (!value || typeof value !== "object")
    throw new Error("証明JSONの形式を確認してください。");
  const object = value as Partial<ProofBundle> & { method?: string };
  const proof = object.proof;
  if (
    !proof ||
    proof.protocol !== "groth16" ||
    !["bn128", "bn254"].includes(proof.curve)
  )
    throw new Error("Groth16 / BN254形式の証明が必要です。");
  const decimal = (v: unknown) =>
    typeof v === "string" && /^(0|[1-9][0-9]{0,77})$/.test(v);
  if (
    !Array.isArray(proof.pi_a) ||
    proof.pi_a.length !== 3 ||
    !proof.pi_a.every(decimal) ||
    !Array.isArray(proof.pi_c) ||
    proof.pi_c.length !== 3 ||
    !proof.pi_c.every(decimal) ||
    !Array.isArray(proof.pi_b) ||
    proof.pi_b.length !== 3 ||
    !proof.pi_b.every(
      (row) => Array.isArray(row) && row.length === 2 && row.every(decimal),
    ) ||
    !Array.isArray(object.publicSignals) ||
    !object.publicSignals.length ||
    object.publicSignals.length > 256 ||
    !object.publicSignals.every(decimal)
  ) {
    throw new Error("証明の座標と公開入力は10進数の文字列で指定してください。");
  }
  return {
    circuit:
      object.circuit ||
      (object.method ? `csi_${object.method}` : defaultCircuit),
    proof: {
      protocol: proof.protocol,
      curve: proof.curve,
      pi_a: proof.pi_a,
      pi_b: proof.pi_b,
      pi_c: proof.pi_c,
    },
    publicSignals: object.publicSignals,
  };
}
