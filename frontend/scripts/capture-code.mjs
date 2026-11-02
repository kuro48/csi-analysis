import { chromium } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const source = readFileSync(
  resolve(root, "backend/contracts/VerifiedProofRegistry.sol"),
  "utf8",
).split("\n");
const escaped = (value) =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
const lines = source
  .map(
    (line, index) =>
      `<div class="line ${index >= 54 && index <= 60 ? "focus" : ""}"><span>${index + 1}</span><code>${escaped(line) || " "}</code></div>`,
  )
  .slice(40, 66)
  .join("");
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1420, height: 960 },
  deviceScaleFactor: 1,
});
await page.setContent(
  `<html><head><meta charset="utf-8"><style>body{margin:0;background:#0e1d19;color:#d7e7dd;font:15px system-ui;padding:48px}header{display:flex;justify-content:space-between;align-items:center;margin-bottom:32px}small{color:#92b9a1;letter-spacing:3px;font-size:12px}h1{font-size:30px;font-weight:500;letter-spacing:-.5px;margin:12px 0}p{color:#a8c0ae;font-size:14px}.badge{border:1px solid #496555;border-radius:8px;padding:12px 20px;font-size:13px}.editor{border:1px solid #344b3c;border-radius:14px;overflow:hidden;background:#14261f}.bar{background:#1e3428;padding:15px 22px;color:#a5c2ae;font-size:13px;border-bottom:1px solid #344b3c}.code{padding:20px 0}.line{display:flex;min-height:23px;line-height:23px;font-size:13px;white-space:pre}.line>span{width:55px;text-align:right;padding-right:25px;color:#617d69}.line code{font-family:ui-monospace,monospace;color:#d1e3d6}.focus{background:#2f543c55;border-left:3px solid #8dc9a0}.focus>span{width:52px}footer{display:flex;justify-content:space-between;color:#88a891;font-size:12px;margin-top:26px}</style></head><body><header><div><small>IMPLEMENTATION / ON-CHAIN VERIFICATION</small><h1>Verify first. Record only on success.</h1><p>Groth16 proof verification and registry write execute in the same EVM transaction.</p></div><span class="badge">CSI Proof · Code evidence</span></header><div class="editor"><div class="bar">backend/contracts/VerifiedProofRegistry.sol</div><div class="code">${lines}</div></div><footer><span>Actual implementation · no manual verification flag</span><span>Solidity / immutable circuit bindings / proof replay protection</span></footer></body></html>`,
);
mkdirSync(resolve(root, "docs/progress/onchain/evidence"), { recursive: true });
await page.screenshot({
  path: resolve(root, "docs/progress/onchain/evidence/08-contract-code.png"),
  fullPage: true,
});
await browser.close();
