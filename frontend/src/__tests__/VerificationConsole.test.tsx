import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { VerificationConsole } from "../../app/verify/VerificationConsole";

beforeEach(() => {
  window.history.replaceState({}, "", "/");
  localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          connected: false,
          message: "検証コントラクトが未設定です",
          circuits: [],
        }),
      }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("never enables sending when the chain is unavailable, even after consent", async () => {
  render(<VerificationConsole />);
  await screen.findByText("未接続");
  fireEvent.click(screen.getByRole("checkbox"));
  expect(
    screen.getByRole("button", { name: "オンチェーンで検証する" }),
  ).toBeDisabled();
  expect(screen.queryByText("オンチェーン検証済み")).not.toBeInTheDocument();
});

test("missing wallet is actionable and cannot produce a success state", async () => {
  render(<VerificationConsole />);
  fireEvent.click(screen.getByRole("button", { name: "ウォレットを接続" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      "EVM対応のブラウザウォレット",
    ),
  );
  expect(screen.queryByText("オンチェーン検証済み")).not.toBeInTheDocument();
});

test("proof JSON import rejects numeric field elements before enabling send", async () => {
  render(<VerificationConsole />);
  const file = new File(["{}"], "invalid-proof.json", {
    type: "application/json",
  });
  Object.defineProperty(file, "text", {
    value: async () =>
      JSON.stringify({
        proof: { protocol: "groth16", curve: "bn128", pi_a: [1, 2, 1] },
        publicSignals: [1],
      }),
  });
  fireEvent.change(screen.getByLabelText("証明JSONファイル"), {
    target: { files: [file] },
  });
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("10進数の文字列"),
  );
  expect(
    screen.getByRole("button", { name: "オンチェーンで検証する" }),
  ).toBeDisabled();
});
