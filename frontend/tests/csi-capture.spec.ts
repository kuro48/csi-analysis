import { test, expect } from "@playwright/test";
import { resolve } from "node:path";
import { mkdirSync, writeFileSync } from "node:fs";

test("real CSI capture: UI generation to confirmed local EVM receipt", async ({
  page,
  request,
}) => {
  test.skip(
    !process.env.E2E_CSI_FILE || process.env.E2E_LOCAL_CHAIN !== "true",
    "Explicit local capture and local EVM required",
  );
  const rpc = process.env.E2E_RPC_URL || "http://127.0.0.1:18545";
  const network = await request.post(rpc, {
    data: { jsonrpc: "2.0", id: 1, method: "eth_chainId", params: [] },
  });
  expect(["0x7a69", "0x539"]).toContain((await network.json()).result);
  await page.exposeFunction(
    "testWalletRPC",
    async (payload: { method: string; params?: unknown[] }) => {
      const response = await request.post(rpc, {
        data: {
          jsonrpc: "2.0",
          id: 1,
          method:
            payload.method === "eth_requestAccounts"
              ? "eth_accounts"
              : payload.method,
          params: payload.params || [],
        },
      });
      const result = await response.json();
      if (result.error) throw new Error(result.error.message);
      return result.result;
    },
  );
  await page.addInitScript(() => {
    const target = window as unknown as {
      ethereum: unknown;
      testWalletRPC: (payload: unknown) => Promise<unknown>;
    };
    target.ethereum = {
      request: (payload: unknown) => target.testWalletRPC(payload),
      on: () => {},
      removeListener: () => {},
    };
  });
  await page.goto("/");
  await expect(page.getByText("Local EVM", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "CSIから証明を生成", exact: true })
    .click();
  // This fallback is accepted only by a DEBUG local backend with PUBLIC_MODE=false.
  await page
    .getByPlaceholder("解析権限を持つトークンを入力")
    .fill(process.env.E2E_OPERATOR_TOKEN || "local-test-only");
  await page
    .getByLabel("CSIファイル", { exact: true })
    .setInputFiles(process.env.E2E_CSI_FILE!);
  await expect(
    page.getByText(
      "証明を生成しました。公開入力を確認し、ウォレットから送信してください。",
    ),
  ).toBeVisible({ timeout: 75_000 });
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "オンチェーンで検証する", exact: true })
    .click();
  await expect(
    page.getByText("オンチェーン検証済み", { exact: true }),
  ).toBeVisible({ timeout: 45_000 });
  const output = resolve(__dirname, "../../docs/progress/onchain/evidence");
  mkdirSync(output, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(output, "06-real-csi-verified-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(output, "07-real-csi-verified-mobile.png"),
    fullPage: true,
  });
  const history = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("csi-verified-transactions-v1") || "[]"),
  );
  const receipt = await (
    await request.get(`/api/v2/onchain/transactions/${history[0].hash}`)
  ).json();
  expect(receipt.status).toBe("confirmed");
  writeFileSync(
    resolve(output, "real-csi-local-receipt.json"),
    JSON.stringify(
      {
        source:
          "Existing local PicoScenes capture -> Python analysis -> real Groth16 proof -> local EVM. Test wallet transport; not public-chain deployment.",
        ...receipt,
      },
      null,
      2,
    ),
  );
  // Changing the input must discard the previous proof's success state.
  await page
    .getByRole("button", { name: "証明JSONを読み込む", exact: true })
    .click();
  await expect(
    page.getByText("オンチェーン検証済み", { exact: true }),
  ).toHaveCount(0);
});
