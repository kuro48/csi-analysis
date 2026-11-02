import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const evidence = resolve(__dirname, "../../docs/progress/onchain/evidence");
test("local EVM: proof import, tamper rejection, wallet send, receipt and responsive screenshots", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_LOCAL_CHAIN !== "true",
    "Requires an explicitly enabled isolated local EVM and configured backend",
  );
  mkdirSync(evidence, { recursive: true });
  const rpc = process.env.E2E_RPC_URL || "http://127.0.0.1:18545";
  const chainResponse = await request.post(rpc, {
    data: { jsonrpc: "2.0", id: 1, method: "eth_chainId", params: [] },
  });
  expect(["0x7a69", "0x539"]).toContain((await chainResponse.json()).result);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  // Only the wallet transport is replaced, using an isolated node's unlocked test
  // account. Proof, verification, transaction, event and receipt are all real.
  await page.exposeFunction(
    "testWalletRPC",
    async (payload: { method: string; params?: unknown[] }) => {
      const method =
        payload.method === "eth_requestAccounts"
          ? "eth_accounts"
          : payload.method;
      const allowed = [
        "eth_accounts",
        "eth_chainId",
        "eth_blockNumber",
        "eth_estimateGas",
        "eth_sendTransaction",
        "eth_getTransactionByHash",
        "eth_getTransactionReceipt",
        "eth_getBlockByNumber",
        "eth_gasPrice",
        "eth_maxPriorityFeePerGas",
        "eth_getTransactionCount",
        "eth_call",
      ];
      if (!allowed.includes(method))
        throw new Error(`Unexpected wallet method: ${method}`);
      const response = await request.post(rpc, {
        data: { jsonrpc: "2.0", id: 1, method, params: payload.params || [] },
      });
      const body = await response.json();
      if (body.error) throw new Error(body.error.message);
      return body.result;
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
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, "01-console-desktop.png"),
    fullPage: true,
  });
  const bundle = JSON.parse(
    readFileSync(
      resolve(
        __dirname,
        "../../backend/contracts/build/onchain/synthetic-proof.json",
      ),
      "utf8",
    ),
  );
  const invalid = {
    ...bundle,
    publicSignals: [bundle.publicSignals[0] === "1" ? "0" : "1"],
  };
  await page.getByLabel("証明JSONファイル").setInputFiles({
    name: "tampered-proof.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(invalid)),
  });
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "オンチェーンで検証する", exact: true })
    .click();
  await expect(page.locator("main").getByRole("alert")).toContainText("拒否");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, "02-tampered-proof-rejected.png"),
    fullPage: true,
  });
  await page.getByLabel("証明JSONファイル").setInputFiles({
    name: "synthetic-signal-proof.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(bundle)),
  });
  await page.getByRole("checkbox").check();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, "03-proof-ready.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "オンチェーンで検証する", exact: true })
    .click();
  await expect(
    page.getByText("オンチェーン検証済み", { exact: true }),
  ).toBeVisible({ timeout: 45_000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, "04-onchain-verified-desktop.png"),
    fullPage: true,
  });
  const history = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("csi-verified-transactions-v1") || "[]"),
  );
  expect(history.length).toBeGreaterThan(0);
  const receiptResponse = await request.get(
    `/api/v2/onchain/transactions/${history[0].hash}`,
  );
  const receipt = await receiptResponse.json();
  expect(receipt.status).toBe("confirmed");
  expect(receipt.gasUsed).toBeGreaterThan(200_000);
  writeFileSync(
    resolve(evidence, "local-evm-receipt.json"),
    JSON.stringify(
      {
        source:
          "Synthetic 0.25 Hz input; real Groth16 proof and local EVM transaction. Test wallet adapter; not a public-chain deployment.",
        ...receipt,
      },
      null,
      2,
    ),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, "05-onchain-verified-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.reload();
  await page.getByRole("button", { name: "チェーンで照会 ↗" }).click();
  await expect(
    page.getByText("オンチェーン検証済み", { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("invalid JSON and unavailable chain never display verification success", async ({
  page,
}) => {
  await page.route("**/api/v2/onchain/status", (route) =>
    route.fulfill({
      json: {
        connected: false,
        message: "検証コントラクトが未設定です",
        circuits: [],
      },
    }),
  );
  await page.goto("/");
  await expect(page.getByText("未接続", { exact: true })).toBeVisible();
  await page.getByLabel("証明JSONファイル").setInputFiles({
    name: "invalid.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"proof":{}}'),
  });
  await expect(page.locator("main").getByRole("alert")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "オンチェーンで検証する", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("オンチェーン検証済み", { exact: true }),
  ).toHaveCount(0);
});
