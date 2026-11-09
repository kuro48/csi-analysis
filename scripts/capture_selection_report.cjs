const { chromium, expect } = require('../frontend/node_modules/@playwright/test');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');

async function main() {
  const directory = resolve(process.argv[2] || 'docs/progress/2026-11-09-selection-comparison');
  const results = JSON.parse(readFileSync(resolve(directory, 'results.json')));
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
    await page.goto(pathToFileURL(resolve(directory, 'index.html')).href);
    await expect(page.locator('h1')).toContainText('Circom と Python');
    await expect(page.locator('table').first().locator('tr')).toHaveCount(results.real.length + 1);
    await page.locator('img').evaluateAll(async images => {
      await Promise.all(images.map(image => image.decode()));
      if (images.some(image => image.naturalWidth === 0)) throw Error('Broken plot');
    });
    await page.screenshot({ path: resolve(directory, 'comparison-overview.png') });
    const escape = text => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
    const source = readFileSync(resolve(__dirname, 'evaluate_subcarrier_selection.py'), 'utf8');
    const excerpt = source.slice(source.indexOf('def exact_scores'), source.indexOf('def float_scores'));
    await page.setContent(`<html lang="ja"><meta charset="utf-8"><style>body{background:#173b33;color:#edf5f1;padding:36px;font:17px system-ui}pre{background:#234b40;padding:24px;white-space:pre-wrap;font:16px/1.65 monospace}</style><h1>回路と同じ式を Python の任意精度整数で照合</h1><p>scripts/evaluate_subcarrier_selection.py / 評価専用コード</p><pre>${escape(excerpt)}</pre></html>`);
    await page.screenshot({ path: resolve(directory, 'code-reference.png'), fullPage: true });
    console.log(`Verified ${results.real.length} input records and ${results.real.filter(r => r.circuit).length} plots; saved screenshots.`);
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
