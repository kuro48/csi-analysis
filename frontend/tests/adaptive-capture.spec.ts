import { test, expect } from "@playwright/test";

test("capture UI submits the selected proof profile and ledger", async ({ page }) => {
  let uploaded = "";
  await page.route("**/api/v2/observations/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/capabilities")) {
      await route.fulfill({ json: { adaptive4004: { evm: false, fabric: true } } });
    } else if (url.endsWith("/patients")) {
      await route.fulfill({ json: { patients: [{ id: "11111111-1111-4111-8111-111111111111", label: "テスト患者" }] } });
    } else if (url.endsWith("/captures")) {
      uploaded = route.request().postDataBuffer()?.toString() || "";
      await route.fulfill({ status: 202, json: { id: "capture-test", status: "queued" } });
    } else await route.abort();
  });
  await page.goto("/capture");
  const profile = page.getByLabel("呼吸判定の方式");
  await expect(profile).toHaveValue("legacy");
  await expect(profile.locator('option[value="adaptive4004"]')).toHaveJSProperty("disabled", true);
  await page.getByLabel("証明の記録先").selectOption("fabric");
  await expect(profile.locator('option[value="adaptive4004"]')).toHaveJSProperty("disabled", false);
  await profile.selectOption("adaptive4004");
  await page.getByRole("combobox", { name: "患者", exact: true }).selectOption("11111111-1111-4111-8111-111111111111");
  await page.getByLabel("計測開始時刻（この端末の現地時刻）").fill("2026-05-19T11:49:51");
  await page.getByLabel("CSIファイル", { exact: true }).setInputFiles({ name: "test.csi", mimeType: "application/octet-stream", buffer: Buffer.from("fixture") });
  await page.getByText("解析APIへのアクセス", { exact: false }).click();
  await page.getByLabel("運用者アクセストークン").fill("ui-test-token");
  await page.getByRole("button", { name: "適用", exact: true }).click();
  await page.getByRole("button", { name: "デバッグ用CSIを収集キューへ送信" }).click();
  await expect(page.getByRole("status")).toContainText("収集を受け付けました");
  expect(uploaded).toMatch(/name="proof_profile"\r\n\r\nadaptive4004/);
  expect(uploaded).toMatch(/name="ledger"\r\n\r\nfabric/);
  await page.getByLabel("証明の記録先").selectOption("evm");
  await expect(profile).toHaveValue("legacy");
});
