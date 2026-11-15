// Run on the operator Mac. This renders only the local, self-contained report.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(__dirname, 'artifacts/report-renderer/browsers');
const { chromium } = require('./artifacts/report-renderer/node_modules/playwright');

(async () => {
  const run = path.join(__dirname, '2026-10-19');
  const screenshots = path.join(run, 'screenshots');
  fs.mkdirSync(screenshots, {recursive: true});
  const steps = JSON.parse(fs.readFileSync(path.join(__dirname, 'steps.json'), 'utf8'));
  const browser = await chromium.launch({headless: true,
    executablePath: path.join(__dirname, 'artifacts/report-renderer/browsers/manual-chromium-1194/chrome-mac/headless_shell')});
  const page = await browser.newPage({viewport: {width: 1500, height: 1050}, deviceScaleFactor: 1.5});
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  try {
    await page.goto(pathToFileURL(path.join(run, 'report.html')).href);
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator('.step').count(), steps.length);
    assert.equal(await page.locator('#selector option').count(), steps.length);
    await page.locator('#mode').click();
    assert.equal(await page.locator('body').evaluate(el => el.classList.contains('capture')), true);
    await page.locator('#next').click();
    assert.equal(await page.locator('.step.active').getAttribute('data-step'), steps[1].id);
    await page.locator('#prev').click();
    assert.equal(await page.locator('.step.active').getAttribute('data-step'), steps[0].id);
    const images = [];
    for (let i = 0; i < steps.length; i++) {
      await page.locator('#selector').selectOption(String(i));
      const card = page.locator('.step.active');
      assert.equal(await card.getAttribute('data-step'), steps[i].id);
      const box = await card.boundingBox();
      const overflow = await card.evaluate(el => [...el.querySelectorAll('pre')].some(p => p.scrollWidth > p.clientWidth + 2));
      assert.equal(overflow, false, `Horizontal overflow in step ${steps[i].id}`);
      const name = `step-${steps[i].id}.png`;
      await card.screenshot({path: path.join(screenshots, name), animations: 'disabled'});
      images.push({step: steps[i].id, file: name, width_css: box.width, height_css: box.height});
      console.log(`PNG ${name}: ${Math.round(box.width)} x ${Math.round(box.height)} CSS pixels`);
    }
    await page.locator('#mode').click();
    assert.equal(await page.locator('body').evaluate(el => el.classList.contains('capture')), false);
    await page.pdf({path: path.join(run, 'report.pdf'), format: 'A4', landscape: true,
                   scale: 0.68, printBackground: true, margin: {top: '10mm', bottom: '10mm', left: '10mm', right: '10mm'}});
    assert.deepEqual(errors, []);
    const result = {browser: browser.version(), step_count: steps.length, images,
                    checks: ['DOM card count', 'step selector', 'capture mode toggle', 'previous/next navigation',
                             'no horizontal code overflow', 'no browser JavaScript errors'],
                    pdf: 'report.pdf', passed: true};
    fs.writeFileSync(path.join(run, 'browser-validation.json'), JSON.stringify(result, null, 2));
    console.log(`Browser checks passed. ${steps.length} PNG images and report.pdf generated.`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
