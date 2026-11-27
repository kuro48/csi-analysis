// Capture the live two-host Fabric viewer. Uses only already recorded real observations.
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const base = process.env.FABRIC_VIEWER_URL || "http://100.110.182.121:8085";
const output = resolve(process.argv[2] || "../docs/progress/2026-11-27-fabric-two-host");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 1150 }, timezoneId: "Asia/Tokyo" });
const page = await context.newPage();
const report = { base, capturedAt: new Date().toISOString(), source: "existing real CSI proofs", cases: [] };
try {
  await page.goto(base + "/patients");
  for (const [name, patient, capture, expected] of [
    ["true", "8ff672b0-232e-4f18-8e2d-c68ed27306e5", "71edbd49-c1ca-474e-804f-a4354df9160b", true],
    ["false", "24b55901-1a9b-4418-8d74-6d706eaa8d5a", "de8aa194-5200-4f0f-8b4f-01664b081c56", false],
  ]) {
    await page.getByLabel("患者", { exact: true }).selectOption(patient);
    await page.getByLabel("計測開始時刻", { exact: true }).selectOption(capture);
    if (await page.getByText(/^isNormal:/).count()) throw Error("Result shown before verification");
    if (name === "true") await page.screenshot({ path: resolve(output, "viewer-before-verification.png"), fullPage: true });
    const responsePromise = page.waitForResponse(r => r.url().endsWith(`/measurements/${capture}/verify`));
    const started = performance.now();
    await page.getByRole("button", { name: "証明を検証して結果を取得" }).click();
    const response = await responsePromise;
    await response.finished();
    const elapsed = performance.now() - started;
    const body = await response.json();
    if (response.status() !== 200 || body.status !== "verified" || body.ledger !== "fabric" || body.isNormal !== expected)
      throw Error("Unexpected verification response");
    await page.getByText(`isNormal: ${expected}`, { exact: true }).waitFor();
    await page.getByText("検証先：Hyperledger Fabric", { exact: true }).waitFor();
    await page.screenshot({ path: resolve(output, `viewer-${name}.png`), fullPage: true });
    report.cases.push({ name, patient, capture, httpStatus: response.status(), clickToHttpResponseMs: elapsed, result: body });
  }
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.screenshot({ path: resolve(output, "viewer-mobile.png"), fullPage: true });
  report.mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  if (report.mobileOverflow) throw Error("Mobile layout overflows");
  writeFileSync(resolve(output, "browser-verification.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
} finally { await browser.close(); }
