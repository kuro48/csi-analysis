import { chromium } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '../..');
const source = readFileSync(resolve(root, 'backend/contracts/BreathingObservationRegistry.sol'), 'utf8');
const escape = text => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const lines = source.split('\n').map((line, index) => `<div><span>${index + 1}</span>${escape(line) || ' '}</div>`).slice(38).join('');
const browser = await chromium.launch();
try {
  const page = await browser.newPage({viewport: {width: 1500, height: 1050}});
  await page.setContent(`<html><meta charset="utf-8"><style>body{margin:0;padding:42px;background:#10231d;color:#d8e9de;font:14px system-ui}h1{font-size:28px;font-weight:500}p{color:#9ab8a5}article{padding:24px 18px;border:1px solid #405b4c;border-radius:14px;background:#162f25;font:13px/25px ui-monospace,monospace;white-space:pre}article span{display:inline-block;width:38px;color:#83a78e}footer{margin-top:24px;color:#9ab8a5}</style><h1>Record a proof. Verify before returning the result.</h1><p>Actual source · backend/contracts/BreathingObservationRegistry.sol</p><article>${lines}</article><footer>Invalid or missing proofs revert. A valid zero output returns false.</footer></html>`);
  const directory = resolve(root, 'docs/progress/observations/evidence');
  mkdirSync(directory, {recursive: true});
  await page.screenshot({path: resolve(directory, '03-record-and-verify-code.png'), fullPage: true});
} finally { await browser.close(); }
