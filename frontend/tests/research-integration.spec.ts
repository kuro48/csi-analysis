import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

const evidence = resolve(__dirname, "../../docs/progress/onchain/evidence");
// UI-only fixtures. These tests do not claim to generate or verify a real proof.
const proof = {
  status: "completed",
  isValid: true,
  isNormal: true,
  method: "vmd_approx_fixed_point",
  estimatedBpm: 15,
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
  publicSignals: ["1", "250", "15", "1234", "5678"],
};
const record = {
  id: "ui-integration-fixture",
  device_id: "UIテスト用データ",
  session_id: "fixture-session",
  status: "completed",
  file_size: 2457600,
  created_at: "2026-11-02T01:00:00Z",
  updated_at: "2026-11-02T01:00:00Z",
  raw_data: { privateMarker: "never-transfer-raw-csi" },
  processed_data: {
    status: "partial",
    analysis: {
      breathing_rate_bpm: 15,
      peak_freq_hz: 0.25,
      selected_pc: 0,
      selected_vmd_mode: 1,
    },
    proofs: { python_circom: proof },
  },
};

for (const scenario of ["supported", "undeployed", "mismatch"] as const) {
  test(`existing analysis hands off proof safely: ${scenario}`, async ({
    page,
  }) => {
    const errors: string[] = [];
    const mutations: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (request.method() === "POST") mutations.push(request.url());
    });
    await page.route("**/api/v2/csi-data/**", (route) => {
      if (route.request().headers().authorization !== "Bearer fixture-operator")
        return route.fulfill({
          status: 401,
          json: { detail: "運用者トークンを設定してください" },
        });
      return route.fulfill({
        json: {
          csi_data: [record],
          total: 1,
          page: 1,
          page_size: 20,
          total_pages: 1,
        },
      });
    });
    await page.route("**/api/v2/onchain/status", (route) =>
      route.fulfill({
        json: {
          connected: true,
          networkName: "UI fixture · Sepolia",
          chainId: 11155111,
          registryAddress: "0x1111111111111111111111111111111111111111",
          currentBlock: 1,
          totalVerified: 0,
          confirmationsRequired: 1,
          circuits:
            scenario === "undeployed"
              ? []
              : [
                  {
                    name: "csi_vmd_approx",
                    circuitId: "0x" + "1".repeat(64),
                    address: "0x2222222222222222222222222222222222222222",
                    verificationKeyHash: "0x" + "2".repeat(64),
                    publicSignalCount: scenario === "mismatch" ? 3 : 5,
                  },
                ],
        },
      }),
    );
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "CSI呼吸解析モニター" }),
    ).toBeVisible();
    await page.locator("summary").click();
    await page.getByLabel("運用者アクセストークン").fill("fixture-operator");
    await page.getByRole("button", { name: "適用", exact: true }).click();
    const handoff = page.getByRole("button", {
      name: "この証明をオンチェーンで検証 →",
    });
    await expect(handoff).toBeEnabled();
    if (scenario === "supported") {
      await handoff.scrollIntoViewIfNeeded();
      await page.screenshot({
        path: resolve(evidence, "10-research-proof-action-fixture.png"),
        fullPage: true,
      });
    }
    await handoff.click();
    await expect(
      page.getByText("解析結果から引き継いだ証明", { exact: true }),
    ).toBeVisible();
    await expect(page).toHaveURL(/\/verify$/);
    await expect(
      page.getByText("csi_vmd_approx", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("checkbox")).not.toBeChecked();
    const submit = page.getByRole("button", {
      name: "オンチェーンで検証する",
      exact: true,
    });
    await expect(submit).toBeDisabled();
    expect(
      await page.evaluate(() =>
        Object.keys(sessionStorage).filter((key) =>
          key.startsWith("csi-proof-handoff:"),
        ),
      ),
    ).toEqual([]);
    expect(
      await page.evaluate(() => JSON.stringify(localStorage)),
    ).not.toContain("fixture-operator");
    await page.getByRole("checkbox").check();
    if (scenario === "supported") {
      await expect(submit).toBeEnabled();
      await page.screenshot({
        path: resolve(evidence, "11-research-proof-import-fixture.png"),
        fullPage: true,
      });
      await page.setViewportSize({ width: 390, height: 844 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: resolve(evidence, "12-research-proof-import-mobile-fixture.png"),
        fullPage: true,
      });
    } else {
      await expect(submit).toBeDisabled();
      await expect(
        page.getByText(
          scenario === "mismatch"
            ? /公開入力数がデプロイ済み回路と一致しません/
            : /この回路は接続先にデプロイされていません/,
        ),
      ).toBeVisible();
    }
    // Returning through client navigation preserves in-memory authentication.
    await page.getByRole("link", { name: "CSI解析モニター" }).click();
    await expect(
      page.getByRole("button", { name: /UIテスト用データ/ }),
    ).toBeVisible();
    await page.locator("summary").click();
    await page.getByRole("button", { name: "解除", exact: true }).click();
    await expect(
      page.getByRole("button", { name: /UIテスト用データ/ }),
    ).toHaveCount(0);
    expect(mutations).toEqual([]);
    expect(errors).toEqual([]);
  });
}
