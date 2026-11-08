// Live local integration evidence. Never intercepts or mocks API responses.
import { chromium, expect } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '../..');
const work = resolve(root, '.local/circom-adaptive-4004');
const evidence = resolve(root, 'docs/progress/2026-11-09-adaptive-4004');
const base = process.env.EVIDENCE_UI_URL || 'http://127.0.0.1:3011';
const api = process.env.EVIDENCE_API_URL || 'http://127.0.0.1:8011/api/v2/observations';
const jobsPath = resolve(work, 'ui-jobs.json');
const mode = process.argv[2];
if (!['enqueue', 'capture', 'code'].includes(mode)) throw Error('Use enqueue (live writes), capture (verify saved jobs), or code');
mkdirSync(evidence, { recursive: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, timezoneId: 'Asia/Tokyo' });
  if (mode === 'code') {
    const escape = s => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
    for (const [filename, first, last, title, output] of [
      ['zkp/circuits/csi_motion_selector.circom', 98, 135, 'Circom内でスコア比較・選択を拘束', 'code-selection.png'],
      ['backend/contracts/AdaptiveBreathingObservationRegistry.sol', 63, 75, '保存済み証明を検証した後だけisNormalを返す', 'code-verification.png'],
    ]) {
      const lines = readFileSync(resolve(root, filename), 'utf8').split('\n').slice(first - 1, last);
      await page.setContent(`<html lang="ja"><meta charset="utf-8"><style>body{margin:0;padding:48px;background:#10271f;color:#e3efe8;font:16px system-ui}h1{font-size:30px}p{color:#a9cdbb}pre{background:#19392c;padding:28px;border:1px solid #446958;border-radius:12px;font:15px/1.7 ui-monospace,monospace;white-space:pre-wrap}small{color:#a9cdbb}</style><small>CSI / 実装コード</small><h1>${title}</h1><p>${filename}</p><pre>${lines.map((line, i) => escape(String(first + i).padStart(3) + '  ' + line)).join('\n')}</pre><small>リポジトリの実ファイルから生成した抜粋</small></html>`);
      await page.screenshot({ path: resolve(evidence, output), fullPage: true });
    }
  } else if (mode === 'enqueue') {
    const token = readFileSync(resolve(work, 'operator.token'), 'utf8').trim();
    const created = await fetch(api + '/patients', { method: 'POST', headers: { Authorization: 'Bearer ' + token } });
    if (!created.ok) throw Error('Patient creation failed');
    const patient = await created.json();
    const jobs = { patient, captures: [] };
    for (const ledger of ['fabric', 'evm']) {
      await page.goto(base + '/capture');
      await page.getByLabel('証明の記録先').selectOption(ledger);
      await expect(page.getByLabel('呼吸判定の方式').locator('option[value="adaptive4004"]')).toHaveJSProperty('disabled', false);
      await page.getByLabel('呼吸判定の方式').selectOption('adaptive4004');
      await page.getByRole('combobox', { name: '患者', exact: true }).selectOption(patient.id);
      await page.getByLabel('計測開始時刻（この端末の現地時刻）').fill('2026-05-19T11:49:51');
      await page.getByLabel('CSIファイル', { exact: true }).setInputFiles(resolve(root, 'sampledata/csi_20260519_114943.csi'));
      await page.getByText('解析APIへのアクセス', { exact: false }).click();
      await page.getByLabel('運用者アクセストークン').fill(token);
      await page.getByRole('button', { name: '適用', exact: true }).click();
      const response = page.waitForResponse(r => r.url() === api + '/captures' && r.request().method() === 'POST');
      await page.getByRole('button', { name: 'デバッグ用CSIを収集キューへ送信' }).click();
      const result = await response;
      if (result.status() !== 202) throw Error('Capture enqueue failed: ' + await result.text());
      jobs.captures.push({ ledger, ...await result.json() });
      writeFileSync(jobsPath, JSON.stringify(jobs, null, 2));
      await page.getByText('解析APIへのアクセス', { exact: false }).click();
      await expect(page.getByRole('status')).toContainText('収集を受け付けました');
      await page.screenshot({ path: resolve(evidence, `capture-${ledger}.png`), fullPage: true });
    }
  } else {
    const jobs = JSON.parse(readFileSync(jobsPath));
    const results = [];
    for (const capture of jobs.captures.filter(c => !process.env.EVIDENCE_LEDGER || c.ledger === process.env.EVIDENCE_LEDGER)) {
      await page.goto(base + '/patients');
      await page.getByLabel('患者', { exact: true }).selectOption(jobs.patient.id);
      await page.getByLabel('計測開始時刻', { exact: true }).selectOption(capture.id);
      await expect(page.getByRole('region', { name: '呼吸判定結果' })).toHaveCount(0);
      await page.screenshot({ path: resolve(evidence, `before-verify-${capture.ledger}.png`), fullPage: true });
      const response = page.waitForResponse(r => r.url().endsWith(`/measurements/${capture.id}/verify`));
      await page.getByRole('button', { name: '証明を検証して結果を取得' }).click();
      const reply = await response;
      const result = await reply.json();
      if (!reply.ok() || result.status !== 'verified') throw Error(JSON.stringify(result));
      results.push({ capture: { id: capture.id, ledger: capture.ledger }, result });
      await expect(page.getByRole('region', { name: '呼吸判定結果' })).toBeVisible();
      await page.screenshot({ path: resolve(evidence, `verified-${capture.ledger}.png`), fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({ path: resolve(evidence, `verified-${capture.ledger}-mobile.png`), fullPage: true });
      await page.setViewportSize({ width: 1440, height: 1100 });
    }
    writeFileSync(resolve(evidence, 'ui-verification.json'), JSON.stringify({ apiMocked: false, patient: jobs.patient, acceptedCaptures: jobs.captures, results }, null, 2));
  }
} finally { await browser.close(); }
