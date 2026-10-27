// Takes the README screenshots of Mortar, against a stand-in GitHub that describes the real release
// (real file names and sizes). Nothing is downloaded or written.
//   xvfb-run -a node test/screenshots.cjs OUTPUT_DIR
const { _electron: electron } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');

const out = path.resolve(process.argv[2] || 'shots');
fs.mkdirSync(out, { recursive: true });
const SIZES = { 'Tessera-Live.iso': 16963215360, 'Tessera-Live-amd-intel.iso': 10571241472, 'Tessera-Live-nvidia.iso': 11181635584, 'Tessera-Live-nvidia-open.iso': 11147788288, 'Tessera-Live-online.iso': 5333053440 };
const PART = 1900 * 1024 * 1024;

(async () => {
  let base;
  const server = http.createServer((req, res) => {
    if (req.url.startsWith('/repos/')) {
      const assets = [];
      for (const [name, size] of Object.entries(SIZES)) {
        for (let i = 0, left = size; left > 0; i++, left -= PART) assets.push({ name: `${name}.part${String(i).padStart(2, '0')}`, size: Math.min(PART, left), browser_download_url: `${base}/x` });
        assets.push({ name: `${name}.sha256`, size: 90, browser_download_url: `${base}/sha` });
      }
      res.setHeader('Content-Type', 'application/json');
      return res.end(JSON.stringify([{ tag_name: 'usb-20261027-1915-9148472', name: 'Tessera USB (test) 2026-10-27', published_at: '2026-10-27T19:15:00Z', prerelease: true, html_url: '', assets }]));
    }
    res.end(`${'0'.repeat(64)}  x\n`);
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
  const drives = [
    { id: '/dev/sdb', name: 'SanDisk Ultra Flair', size: 31914983424, mounts: [], bus: 'USB' },
    { id: '/dev/sdc', name: 'Kingston DataTraveler', size: 15518924800, mounts: [], bus: 'USB' },
    { id: '/dev/sdd', name: 'PNY Attaché', size: 7743995904, mounts: [], bus: 'USB' },
  ];
  const app = await electron.launch({
    executablePath: process.env.ELECTRON || require('electron'),
    args: ['--no-sandbox', path.join(__dirname, '..')],
    env: { ...process.env, MORTAR_API: base, MORTAR_DOWNLOAD_DIR: fs.mkdtempSync(path.join(os.tmpdir(), 'mortar-shots-')),
      MORTAR_FAKE_DRIVES: JSON.stringify(drives), MORTAR_FAKE_GPUS: JSON.stringify([{ vendor: '10de', device: '1c81', name: 'NVIDIA GeForce GTX 1050' }]) },
  });
  try {
    const page = await app.firstWindow();
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(940, 720));
    await page.waitForFunction(() => /built/.test(document.getElementById('imageInfo').textContent) && /GTX 1050/.test(document.getElementById('thisInfo').textContent));
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(out, 'mortar-1-choose.png') });
    await page.click('#optCustom');
    await page.waitForSelector('#flavors:not([hidden]) .choice');
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(out, 'mortar-2-customize.png') });
    await page.click('#back');
    await page.click('#optThis');
    await page.waitForSelector('.drive');
    await page.locator('.drive', { hasText: 'Kingston' }).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(out, 'mortar-3-drive.png') });
    // From here the real "make" is swapped for a stand-in that reports progress and never touches a drive,
    // so the confirm, progress and done screens are the app's own code paths.
    await app.evaluate(({ ipcMain }) => {
      ipcMain.removeHandler('make');
      ipcMain.handle('make', (e) => new Promise((resolve) => {
        const total = 11181635584;
        e.sender.send('progress', { phase: 'download', done: total, total });
        e.sender.send('progress', { phase: 'check', done: total, total });
        e.sender.send('progress', { phase: 'write', done: 0.62 * total, total, rate: 38e6 });
        globalThis.finishMake = () => resolve({ ok: true });
      }));
    });
    await page.click('#go');
    await page.waitForSelector('#confirm:not([hidden])');
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(out, 'mortar-4-confirm.png') });
    await page.click('#confirmYes');
    await page.waitForFunction(() => /Write/.test(document.querySelector('#steps .now')?.textContent || ''));
    await page.evaluate(() => { document.getElementById('workLine').textContent = 'You can keep using your computer. Leave the USB drive plugged in.'; });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(out, 'mortar-5-writing.png') });
    await page.evaluate(() => { t0 = Date.now() - 13.6 * 60000; });
    await app.evaluate(() => globalThis.finishMake());
    await page.waitForSelector('#finished:not([hidden])');
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(out, 'mortar-6-done.png') });
  } finally {
    await app.close();
    server.close();
  }
  console.log('screenshots in', out);
})().catch((e) => { console.error(e); process.exit(1); });
