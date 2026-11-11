// Сборка PDF из solution.html (Chromium через Playwright).
// KaTeX подставляется из локального пакета, чтобы сборка работала без доступа к CDN:
//   npm install katex@0.16.11   (в любой папке)
//   KATEX_DIR=/путь/к/node_modules/katex/dist node build_pdf.js
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const here = __dirname;
const katexDir = process.env.KATEX_DIR;
const out = path.join(here, process.argv[2] || 'RGR_variant7_solution.pdf');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  if (katexDir) {
    await page.route('https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/**', async (route) => {
      const rel = new URL(route.request().url()).pathname.split('/dist/')[1];
      const file = path.join(katexDir, rel);
      const type = rel.endsWith('.css') ? 'text/css' : rel.endsWith('.js') ? 'application/javascript'
        : rel.endsWith('.woff2') ? 'font/woff2' : rel.endsWith('.woff') ? 'font/woff' : 'font/ttf';
      await route.fulfill({ status: 200, contentType: type, body: fs.readFileSync(file) });
    });
  }
  await page.goto('file://' + path.join(here, 'solution.html'), { waitUntil: 'networkidle' });
  await page.waitForSelector('body[data-math="done"]', { timeout: 30000 });
  await page.evaluate(() => document.fonts.ready);
  const errors = await page.$$eval('.katex-error', (els) => els.map((e) => e.textContent));
  if (errors.length) { console.error('KaTeX errors:', errors); process.exit(1); }
  await page.emulateMedia({ media: 'print' });
  await page.setViewportSize({ width: 660, height: 1000 }); // ширина текста страницы A4 при печати
  const overflow = await page.$$eval('.katex-display', (els) => els
    .map((e, i) => ({ i, over: e.scrollWidth - e.clientWidth, text: e.querySelector('annotation')?.textContent.slice(0, 70) }))
    .filter((o) => o.over > 1));
  if (overflow.length) console.warn('Слишком широкие формулы:', overflow);
  await page.pdf({
    path: out,
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: '<div style="width:100%;font-size:9px;color:#777;text-align:center;font-family:serif;">'
      + 'Типовой расчёт, вариант 7 — стр. <span class="pageNumber"></span> из <span class="totalPages"></span></div>',
  });
  await browser.close();
  console.log('PDF:', out);
})();
