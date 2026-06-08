const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const net = [];
  p.on('response', async r => {
    if (r.url().includes('openrouteservice')) {
      let bodyLen = -1, errTxt = '';
      try { const t = await r.text(); bodyLen = t.length; if (!r.ok()) errTxt = t.slice(0, 300); } catch (e) {}
      net.push(`${r.status()} len=${bodyLen} ${r.url()} ${errTxt}`);
    }
  });
  p.on('console', m => { if (m.type() === 'error') net.push('CONSOLE_ERR ' + m.text()); });
  p.on('requestfailed', r => { if (r.url().includes('openrouteservice')) net.push('REQFAIL ' + r.failure()?.errorText + ' ' + r.url()); });

  await p.goto('http://localhost:8080/', { waitUntil: 'networkidle', timeout: 60000 });
  await p.waitForSelector('#map canvas');
  await p.waitForTimeout(3500);
  await p.click('button[data-view="here"]');
  await p.waitForTimeout(800);
  await p.mouse.click(720, 480);
  await p.waitForTimeout(1500);
  const toast1 = await p.textContent('#toast').catch(() => '');
  await p.waitForTimeout(6000);
  const toast2 = await p.textContent('#toast').catch(() => '');
  await b.close();
  console.log('ORS_NET:', net.length ? net.join('\n') : '(no openrouteservice request seen)');
  console.log('TOAST@1.5s:', JSON.stringify(toast1));
  console.log('TOAST@7.5s:', JSON.stringify(toast2));
})().catch(e => { console.error('FATAL', e); process.exit(1); });
