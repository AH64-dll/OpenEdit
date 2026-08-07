// Contract Guard functional smoke test — retro-CRT redesign of OpenEdit front-end.
// Run from the open-design e2e dir so '@playwright/test' resolves:
//   cd /home/amr/Documents/open-design/e2e && node /home/amr/apps/mlt-pipeline/docs/redesign/crt/contract_guard/smoke.mjs
import { chromium } from '/home/amr/Documents/open-design/e2e/node_modules/@playwright/test/index.mjs';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const outDir = path.dirname(fileURLToPath(import.meta.url));
const BASE = 'http://127.0.0.1:8000';
const results = { checks: [], consoleErrors: [], pageErrors: [], ok: true };

function check(name, pass, detail = '') {
  results.checks.push({ name, pass: !!pass, detail });
  if (!pass) results.ok = false;
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

const browser = await chromium.launch({
  executablePath: '/usr/bin/google-chrome-stable',
  headless: true,
  args: ['--no-sandbox', '--disable-gpu'],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

page.on('console', (m) => {
  if (m.type() === 'error') results.consoleErrors.push(m.text());
});
page.on('pageerror', (e) => results.pageErrors.push(String(e)));

try {
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('#project-select', { timeout: 15000 });
  check('page loads, #project-select exists', true);

  // project select populates (placeholder option exists initially — wait for a real one)
  await page.waitForFunction(
    () => [...document.querySelectorAll('#project-select option')].some(o => o.value !== ''),
    { timeout: 20000 }
  );
  await page.waitForTimeout(600); // let the list settle
  const options = await page.evaluate(() => [...document.querySelectorAll('#project-select option')].map(o => o.value));
  const labels = await page.evaluate(() => [...document.querySelectorAll('#project-select option')].map(o => o.textContent));
  const optionCount = options.length;
  check('project-select populates', optionCount > 0, `options=${optionCount} [${labels.join(', ')}]`);
  check('e2e-demo project present', labels.some(t => t.includes('e2e-demo')), `labels=${labels.join(', ')}`);

  // select e2e-demo (option value is the project id — resolve via label)
  const demoValue = await page.evaluate(() => {
    const o = [...document.querySelectorAll('#project-select option')].find(x => x.textContent.includes('e2e-demo'));
    return o ? o.value : null;
  });
  check('resolve e2e-demo option value', !!demoValue, demoValue ?? '');
  await page.selectOption('#project-select', demoValue);
  await page.waitForSelector('.timeline-clip', { timeout: 20000 }).catch(() => {});
  const clipCount = await page.evaluate(() => document.querySelectorAll('.timeline-clip').length);
  check('timeline-clips appear after selecting e2e-demo', clipCount > 0, `clips=${clipCount}`);

  // initial theme
  const themeBefore = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  const bgBefore = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  console.log(`  initial data-theme=${themeBefore} bodyBg=${bgBefore}`);

  // theme toggle flips data-theme AND body background changes
  await page.click('#btn-toggle-theme');
  await page.waitForTimeout(700); // transition
  const themeAfter = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  const bgAfter = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check('theme toggle flips data-theme', themeAfter !== themeBefore, `${themeBefore} -> ${themeAfter}`);
  check('body background changes', bgAfter !== bgBefore, `${bgBefore} -> ${bgAfter}`);

  // screenshot light
  await page.screenshot({ path: path.join(outDir, 'light.png') });

  // toggle back to dark
  await page.click('#btn-toggle-theme');
  await page.waitForTimeout(700);
  const themeBack = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  check('toggle back to dark works', themeBack === themeBefore, `${themeAfter} -> ${themeBack}`);
  await page.screenshot({ path: path.join(outDir, 'dark.png') });

  // extra: timeline panels / chat presence
  const chatVisible = await page.evaluate(() => !!document.querySelector('#chat-log'));
  const rendersVisible = await page.evaluate(() => !!document.querySelector('#renders-list'));
  check('chat-log present', chatVisible);
  check('renders-list present', rendersVisible);
} catch (e) {
  results.ok = false;
  results.fatal = String(e);
  console.error('FATAL:', e);
  try { await page.screenshot({ path: path.join(outDir, 'error.png') }); } catch {}
} finally {
  await browser.close();
}

check('no pageerror events', results.pageErrors.length === 0, results.pageErrors.slice(0, 3).join(' | '));
const realConsoleErrors = results.consoleErrors.filter(e => !/404/.test(e));
check('no console errors (excluding transient 404s)', realConsoleErrors.length === 0,
  (realConsoleErrors.length ? realConsoleErrors.slice(0, 3).join(' | ') : '') +
  (results.consoleErrors.length ? ` (${results.consoleErrors.length} console errors total, 404s tolerated)` : ''));

const { writeFile } = await import('node:fs/promises');
await writeFile(path.join(outDir, 'smoke-results.json'), JSON.stringify(results, null, 2));
console.log('\nSUMMARY:', results.ok ? 'ALL PASS' : 'FAILURES PRESENT');
console.log('results written to', path.join(outDir, 'smoke-results.json'));
process.exit(results.ok ? 0 : 1);
