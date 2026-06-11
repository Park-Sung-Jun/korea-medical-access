// #trend 섹션 렌더 검증 + 스크린샷
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE ' + m.text()); });
  page.on('pageerror', e => errors.push('PAGEERROR ' + e.message));

  await page.goto('http://localhost:8080/index.html#trend', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(3500);
  await page.locator('#trend').scrollIntoViewIfNeeded();
  await page.waitForTimeout(1500);
  const corr = (await page.textContent('#trendCorr')).trim().slice(0, 120);
  const hasCanvas = await page.locator('#chartTrend canvas').count() > 0
    && await page.locator('#chartSexGap canvas').count() > 0;
  await page.locator('#trend').screenshot({ path: path.join(__dirname, '..', 'screenshots', 'trend.png') });
  await browser.close();
  console.log('CORR:', corr);
  console.log('CANVAS:', hasCanvas);
  console.log('ERRORS:', errors.length ? JSON.stringify(errors) : 'none');
})().catch(e => { console.error('FATAL', e); process.exit(1); });
