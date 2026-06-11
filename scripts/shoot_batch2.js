// 연령 차트(#chartAge) + 지도 센터급 응급 토글 검증
const { chromium } = require('playwright');
const path = require('path');
const OUT = path.join(__dirname, '..', 'screenshots');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE ' + m.text()); });
  page.on('pageerror', e => errors.push('PAGEERROR ' + e.message));

  // 1) 리포트 연령 차트
  await page.goto('http://localhost:8080/index.html#trend', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(3000);
  await page.locator('#trend').scrollIntoViewIfNeeded();
  await page.waitForTimeout(1200);
  const ageCanvas = await page.locator('#chartAge canvas').count() > 0;
  await page.locator('#trend').screenshot({ path: path.join(OUT, 'trend2.png') });

  // 2) 지도 er 뷰 → 센터급 토글
  await page.goto('http://localhost:8080/map.html', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForSelector('#map canvas', { timeout: 30000 });
  await page.waitForTimeout(3500);
  await page.click('button[data-view="er"]');
  await page.waitForTimeout(1500);
  const rowVisible = await page.locator('#er-tier-row').isVisible();
  await page.screenshot({ path: path.join(OUT, 'er_desig.png') });
  await page.check('#toggle-ercenter');
  await page.waitForTimeout(1500);
  const legend = (await page.textContent('#legend')).slice(0, 80);
  await page.screenshot({ path: path.join(OUT, 'er_center.png') });

  await browser.close();
  console.log('AGE CANVAS:', ageCanvas, '| TIER ROW:', rowVisible);
  console.log('LEGEND(center):', legend.replace(/\s+/g, ' '));
  console.log('ERRORS:', errors.length ? JSON.stringify(errors) : 'none');
})().catch(e => { console.error('FATAL', e); process.exit(1); });
