// Opt-in browser-to-chain integration. Arguments: CSI file, operator token file, output JSON.
import {
  chromium,
  expect,
} from "../../frontend/node_modules/@playwright/test/index.mjs";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
const browser = await chromium.launch();
try {
  const context = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:3000",
  });
  const page = await context.newPage();
  const token = readFileSync(process.argv[3], "utf8").trim();
  const headers = { Authorization: "Bearer " + token };
  const patientResponse = await context.request.post(
    "/api/v2/observations/patients",
    { headers },
  );
  expect(patientResponse.status()).toBe(201);
  const patient = (await patientResponse.json()).id;
  await page.goto("/capture");
  await page.getByText("解析APIへのアクセス", { exact: false }).click();
  await page.getByLabel("運用者アクセストークン").fill(token);
  await page.getByRole("button", { name: "適用", exact: true }).click();
  await page.getByLabel("証明の記録先").selectOption("fabric");
  await page.locator("select").nth(1).selectOption(patient);
  const d = new Date(Date.now() - 65000),
    pad = (x) => String(x).padStart(2, "0");
  const local = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  await page.getByLabel("計測開始時刻（この端末の現地時刻）").fill(local);
  await page.getByLabel("CSIファイル").setInputFiles(resolve(process.argv[2]));
  const accepted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v2/observations/captures") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "デバッグ用CSIを収集キューへ送信" })
    .click();
  const response = await accepted;
  expect(response.status()).toBe(202);
  const capture = (await response.json()).id;
  await expect
    .poll(
      async () => {
        const r = await context.request.get(
          "/api/v2/observations/captures/" + capture,
          { headers },
        );
        return (await r.json()).status;
      },
      { timeout: 120000, intervals: [1000, 2000] },
    )
    .toBe("recorded");
  await page.goto("/patients");
  await page.getByLabel("患者", { exact: true }).selectOption(patient);
  await page.getByLabel("計測開始時刻", { exact: true }).selectOption(capture);
  await expect(page.getByText(/isNormal:/)).toHaveCount(0);
  const verification = page.waitForResponse((r) =>
    r.url().endsWith("/measurements/" + capture + "/verify"),
  );
  await page.getByRole("button", { name: "証明を検証して結果を取得" }).click();
  const result = await (await verification).json();
  expect(result.status).toBe("verified");
  expect(result.ledger).toBe("fabric");
  await expect(
    page.getByText("isNormal: " + result.isNormal, { exact: true }),
  ).toBeVisible();
  const evidence = {
    kind: "real-browser-csi-capture-to-fabric",
    patient,
    capture,
    result,
  };
  writeFileSync(process.argv[4], JSON.stringify(evidence, null, 2) + "\n");
  console.log(
    JSON.stringify({
      capture,
      status: result.status,
      ledger: result.ledger,
      isNormal: result.isNormal,
    }),
  );
} finally {
  await browser.close();
}
