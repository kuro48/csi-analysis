// Uses the REAL API through the existing UI; no mocked verification result.
import { chromium } from "../../frontend/node_modules/@playwright/test/index.mjs";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
const root = resolve(import.meta.dirname, "../..");
const evidence = resolve(root, "docs/progress/fabric/evidence");
mkdirSync(evidence, { recursive: true });
const ids = JSON.parse(
  readFileSync(resolve(root, ".local/fabric/api-evidence-ids.json")),
);
const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  await page.goto("http://127.0.0.1:3000/patients");
  await page.getByLabel("患者", { exact: true }).selectOption(ids.patient);
  await page
    .getByLabel("計測開始時刻", { exact: true })
    .selectOption(ids.capture);
  await page.getByRole("button", { name: "証明を検証して結果を取得" }).click();
  await page.getByRole("region", { name: "呼吸判定結果" }).waitFor();
  await page.screenshot({
    path: resolve(evidence, "patient-fabric.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: resolve(evidence, "patient-fabric-mobile.png"),
    fullPage: true,
  });
  if (
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    )
  )
    throw Error("Mobile layout overflow");
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("http://127.0.0.1:3000/capture");
  await page.getByLabel("証明の記録先").selectOption("fabric");
  await page.screenshot({
    path: resolve(evidence, "capture-ledger-selection.png"),
    fullPage: true,
  });
  await page.goto(
    "file://" +
      resolve(process.argv[2] || ".local/fabric/results-paired/report.html"),
  );
  await page.screenshot({
    path: resolve(evidence, "benchmark-report.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: resolve(evidence, "benchmark-report-mobile.png"),
    fullPage: true,
  });
  if (
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    )
  )
    throw Error("Report mobile overflow");
  const source = readFileSync(
    resolve(root, "fabric/chaincode/lib/observations.js"),
    "utf8",
  );
  const lines = source
    .slice(source.indexOf("  async VerifyObservation"))
    .split("\n")
    .slice(0, -2)
    .join("\n");
  const escape = (t) =>
    t.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.setContent(
    `<html><meta charset="utf-8"><style>body{padding:48px;background:#11281f;color:#d6eadf;font:16px system-ui}h1{font-size:30px}small{color:#91b9a3}pre{background:#1d392b;border:1px solid #446b54;border-radius:14px;padding:25px;white-space:pre-wrap;font:15px/1.9 monospace;overflow-wrap:anywhere}</style><small>CSI CARE / FABRIC IMPLEMENTATION</small><h1>記録された証明を、chaincode内で検証する。</h1><p>検証に成功した場合だけ isNormal を返します。</p><pre>${escape(lines)}</pre><small>fabric/chaincode/lib/observations.js · 実装コード</small></html>`,
  );
  await page.screenshot({
    path: resolve(evidence, "chaincode-verification.png"),
    fullPage: true,
  });
  console.log(
    "Saved real UI, comparison report, mobile, and code screenshots.",
  );
} finally {
  await browser.close();
}
