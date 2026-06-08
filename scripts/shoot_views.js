// 4개 뷰 스크린샷 + 콘솔 에러 캡처 (Playwright)
const { chromium } = require('playwright');
const path = require('path');

const OUT = path.join(__dirname, '..', 'screenshots');
const BASE = 'http://localhost:8080/';

(async () => {
  const fs = require('fs');
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE ' + m.text()); });
  page.on('pageerror', e => errors.push('PAGEERROR ' + e.message));

  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForSelector('#map canvas', { timeout: 30000 });
  await page.waitForTimeout(4000); // 타일/데이터 렌더 대기

  const shot = (n) => page.screenshot({ path: path.join(OUT, n) });

  // 1) 접근성 등시선 (기본)
  await shot('1_iso.png');

  // 2) 접근성×고령화
  await page.click('button[data-view="bivar"]');
  await page.waitForTimeout(1500);
  await shot('2_bivar.png');

  // 3) 고령화지수
  await page.click('button[data-view="aging"]');
  await page.waitForTimeout(1500);
  await shot('3_aging.png');

  // 4) 여기서 등시선 → 지도 클릭(대전 부근 중앙) → ORS 응답 대기
  await page.click('button[data-view="here"]');
  await page.waitForTimeout(1200);
  await page.mouse.click(720, 480);           // #map 중앙부 클릭
  // ORS 응답(수백 KB)이 도착해 "완료" 토스트가 뜰 때까지 대기(최대 20s)
  await page.waitForFunction(() => {
    const t = document.getElementById('toast');
    return t && /완료|없습니다|실패|키를 설정/.test(t.textContent);
  }, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(1200);            // 렌더 안정화
  await shot('4_here_click.png');

  // 배지 텍스트 확인
  const badge = await page.textContent('#badge-hosp').catch(() => '(no badge-hosp)');

  await browser.close();
  console.log('BADGE:', (badge || '').trim());
  console.log('ERRORS:', errors.length ? JSON.stringify(errors, null, 2) : 'none');
  console.log('DONE -> ' + OUT);
})().catch(e => { console.error('FATAL', e); process.exit(1); });
