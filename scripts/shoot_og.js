// OG 카드 이미지(1200×630) 생성 — 지도 접근성×고령화(bivar) 뷰 캡처 → ../og.png
const { chromium } = require('playwright');
const path = require('path');

const BASE = 'http://localhost:8080/map.html';
const OUT = path.join(__dirname, '..', 'og.png');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 2 });
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForSelector('#map canvas', { timeout: 30000 });
  await page.waitForTimeout(4000);
  await page.click('button[data-view="bivar"]');
  await page.waitForTimeout(2500);
  await page.screenshot({ path: OUT });
  await browser.close();
  console.log('saved ->', OUT);
})().catch(e => { console.error('FATAL', e); process.exit(1); });
