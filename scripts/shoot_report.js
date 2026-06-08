const { chromium } = require('playwright');
const path = require('path');
const OUT = path.join(__dirname, '..', 'screenshots');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  p.on('pageerror', e => errs.push('PAGEERR ' + e.message));
  await p.goto('http://localhost:8080/report.html', { waitUntil: 'networkidle', timeout: 60000 });
  await p.waitForTimeout(2500);
  const sh = n => p.screenshot({ path: path.join(OUT, n) });

  await sh('r1_hero.png');                                   // KPI 카운트업
  await p.locator('#ohca').scrollIntoViewIfNeeded();
  await p.waitForTimeout(1200);
  await sh('r2_bubble.png');                                 // 버블 차트
  await p.click('#chartSeg button[data-v="split"]');
  await p.waitForTimeout(900);
  await sh('r3_split.png');                                  // 분해 산점도
  await p.locator('#triple').scrollIntoViewIfNeeded();
  await p.waitForTimeout(500);
  await sh('r4_triple.png');                                 // 삼중취약 표
  await p.locator('#map').scrollIntoViewIfNeeded();
  await p.waitForTimeout(2500);
  await sh('r5_map.png');                                    // 임베드 지도

  const kpi = await p.textContent('#kpiCards .kpi .v').catch(()=>'?');
  await b.close();
  console.log('KPI first card:', (kpi||'').trim());
  console.log('ERRORS:', errs.length ? errs.join(' | ') : 'none');
})().catch(e => { console.error('FATAL', e); process.exit(1); });
