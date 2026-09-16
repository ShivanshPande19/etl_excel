const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 3 });
  const fileUrl = 'file://' + path.resolve(__dirname, 'bennett-university-id-cards.html');
  await page.goto(fileUrl, { waitUntil: 'networkidle' });
  // give images a moment to decode
  await page.waitForTimeout(800);

  const cards = await page.$$('.card');
  const slugs = await page.$$eval('.pimg', els => els.map(e => e.dataset.slug));

  for (let i = 0; i < cards.length; i++) {
    const out = path.resolve(__dirname, 'id-cards', slugs[i] + '.png');
    await cards[i].screenshot({ path: out });
    console.log('saved', out);
  }

  // Combined preview of the whole page
  await page.setViewportSize({ width: 1180, height: 900 });
  await page.screenshot({
    path: path.resolve(__dirname, 'preview', 'bennett-id-cards-preview.png'),
    fullPage: true,
  });
  console.log('saved preview');

  await browser.close();
})();
