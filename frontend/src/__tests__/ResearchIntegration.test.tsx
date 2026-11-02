import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ResearchAccess } from "../../app/ResearchAccess";
import { operatorFetch, setOperatorToken } from "../../app/operator-access";
import {
  analysisProofBundle,
  consumeProofHandoff,
  storeProofHandoff,
} from "../../app/verify/handoff";
import { VerifyAnalysisProof } from "../../app/verify/VerifyAnalysisProof";
import type { VerifiableProofResult } from "../../app/upload/types";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

// Structurally valid UI fixture; no claim of cryptographic validity.
const result: VerifiableProofResult = {
  status: "completed",
  isValid: true,
  method: "vmd_approx_fixed_point",
  proof: {
    protocol: "groth16",
    curve: "bn128",
    pi_a: ["1", "2", "1"],
    pi_b: [
      ["1", "2"],
      ["3", "4"],
      ["1", "0"],
    ],
    pi_c: ["1", "2", "1"],
  },
  publicSignals: ["1", "2", "3", "4", "5"],
};
beforeEach(() => {
  setOperatorToken("");
  sessionStorage.clear();
  localStorage.clear();
  push.mockClear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("analysis handoff strips private fields and is consumed only once", () => {
  const enriched = {
    ...result,
    device_id: "private-device",
    raw_data: [123],
    token: "secret",
    proof: { ...result.proof, privateWitness: "secret" },
  };
  const bundle = analysisProofBundle(enriched);
  expect(bundle.circuit).toBe("csi_vmd_approx");
  expect(Object.keys(bundle).sort()).toEqual([
    "circuit",
    "proof",
    "publicSignals",
  ]);
  const id = storeProofHandoff(bundle);
  expect(sessionStorage.getItem(`csi-proof-handoff:${id}`)).not.toMatch(
    /private|secret|raw_data|token/,
  );
  expect(consumeProofHandoff(id)).toEqual(bundle);
  expect(() => consumeProofHandoff(id)).toThrow("見つかりません");
});

test("expired proof handoffs are deleted and rejected", () => {
  const now = Date.now();
  vi.spyOn(Date, "now").mockReturnValue(now);
  const id = storeProofHandoff(analysisProofBundle(result));
  vi.mocked(Date.now).mockReturnValue(now + 600_001);
  expect(() => consumeProofHandoff(id)).toThrow("期限切れ");
  expect(sessionStorage.length).toBe(0);
});

test.each([
  { ...result, status: "failed" as const },
  { ...result, isValid: false },
  { ...result, proof: undefined },
  { ...result, method: "unknown" },
])("unusable analysis proof cannot navigate: %j", (invalid) => {
  render(<VerifyAnalysisProof result={invalid} />);
  const button = screen.getByRole("button");
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(push).not.toHaveBeenCalled();
});

test("proof action transfers the bundle without putting proof data in the URL", () => {
  render(<VerifyAnalysisProof result={result} />);
  fireEvent.click(screen.getByRole("button"));
  const url = push.mock.calls[0][0] as string;
  expect(url).toMatch(/^\/verify\?import=[0-9a-f-]{36}$/);
  expect(consumeProofHandoff(url.split("=")[1])).toEqual(
    analysisProofBundle(result),
  );
});

test("research authentication is shared with API requests and clears on logout", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetch);
  render(<ResearchAccess />);
  fireEvent.change(screen.getByLabelText("運用者アクセストークン"), {
    target: { value: "test-operator" },
  });
  fireEvent.click(screen.getByRole("button", { name: "適用" }));
  await operatorFetch("/api/v2/csi-data/");
  expect(fetch.mock.calls[0][1].headers.get("Authorization")).toBe(
    "Bearer test-operator",
  );
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "解除" }));
  await operatorFetch("/api/v2/csi-data/");
  expect(fetch.mock.calls[1][1].headers.has("Authorization")).toBe(false);
});
