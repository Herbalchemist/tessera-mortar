// Real-Electron check of Mortar's window: a stand-in GitHub (releases API, image parts, checksum)
// and a file standing in for the USB drive. Run as root (writes go straight to the file):
//   xvfb-run -a node test/qa-electron.cjs
const { _electron: electron } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const assert = require('assert/strict');

const out = process.env.QA_OUT || path.join(os.tmpdir(), 'mortar-qa');
fs.mkdirSync(out, { recursive: true });
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mortar-e2e-'));
const data = crypto.randomBytes(6 * 1024 * 1024 + 2048);
const sizes = [2 * 1024 * 1024, 2 * 1024 * 1024, data.length - 4 * 1024 * 1024];
const sha = crypto.createHash('sha256').update(data).digest('hex');

(async () => {
  let base;
  const server = http.createServer((req, res) => {
    if (req.url.startsWith('/repos/')) {
      res.setHeader('Content-Type', 'application/json');
      return res.end(JSON.stringify([{ tag_name: 'usb-20261027-0205-test', name: 'Tessera USB (test)', published_at: '2026-10-27T02:05:00Z', prerelease: true, html_url: 'https://example.invalid',
        assets: [...sizes.map((s, i) => ({ name: `Tessera-Live.iso.part0${i}`, size: s, browser_download_url: `${base}/p/${i}` })), { name: 'Tessera-Live.iso.sha256', size: 90, browser_download_url: `${base}/sha` }] }]));
    }
    if (req.url === '/sha') return res.end(`${sha}  Tessera-Live.iso\n`);
    const i = Number(req.url.split('/').pop());
    const start = sizes.slice(0, i).reduce((a, b) => a + b, 0);
    const part = data.subarray(start, start + sizes[i]);
    const m = /bytes=(\d+)-/.exec(req.headers.range || '');
    const from = m ? Number(m[1]) : 0;
    res.writeHead(m ? 206 : 200, { 'Content-Length': part.length - from });
    // a slow trickle so the progress screen can be seen
    const body = part.subarray(from);
    let o = 0;
    const tick = () => { if (o >= body.length) return res.end(); res.write(body.subarray(o, o + 256 * 1024)); o += 256 * 1024; setTimeout(tick, 60); };
    tick();
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
  const target = path.join(dir, 'usb.bin');
  fs.writeFileSync(target, Buffer.alloc(16 * 1024 * 1024));
  const drives = [
    { id: target, name: 'SanDisk Ultra', size: 32017047552, mounts: ['/run/media/me/STICK'], bus: 'USB' },
    { id: '/dev/sdz', name: 'Tiny Stick', size: 8e9, mounts: [], bus: 'USB' },
  ];
  const app = await electron.launch({
    executablePath: process.env.ELECTRON || require('electron'),
    args: ['--no-sandbox', path.join(__dirname, '..')],
    env: { ...process.env, MORTAR_API: base, MORTAR_DOWNLOAD_DIR: path.join(dir, 'dl'), MORTAR_FAKE_DRIVES: JSON.stringify(drives), MORTAR_TEST_TARGET: target },
  });
  const errors = [];
  try {
    const page = await app.firstWindow();
    page.on('pageerror', (e) => errors.push(String(e)));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(940, 720));
    await page.waitForFunction(() => /built/.test(document.getElementById('imageInfo').textContent));
    await page.waitForSelector('.drive');
    assert.equal(await page.locator('.drive').count(), 2);
    assert.equal(await page.locator('.drive[disabled]').count(), 1, 'the 8 GB stick is too small');
    await page.locator('.drive:not([disabled])').click();
    assert.equal(await page.locator('#go').isEnabled(), true);
    await page.screenshot({ path: path.join(out, '1-setup.png') });
    await page.click('#go');
    await page.waitForSelector('#confirm:not([hidden])');
    assert.match(await page.textContent('#confirmText'), /SanDisk Ultra \(32\.0 GB\) will be erased/);
    await page.screenshot({ path: path.join(out, '2-confirm.png') });
    await page.click('#confirmYes');
    await page.waitForFunction(() => /Download Tessera\d*%/.test(document.getElementById('steps').textContent.replace(/\s/g, '')) || /%/.test(document.getElementById('steps').textContent), null, { timeout: 15000 });
    await page.screenshot({ path: path.join(out, '3-progress.png') });
    await page.waitForSelector('#finished:not([hidden])', { timeout: 120000 });
    const title = await page.textContent('#doneTitle');
    assert.equal(title, 'Your Tessera USB is ready', 'finished: ' + title + ' ' + (await page.textContent('#doneBody')));
    await page.screenshot({ path: path.join(out, '4-done.png') });
    const written = fs.readFileSync(target).subarray(0, data.length);
    assert.ok(written.equals(data), 'the "USB" holds the image');
    console.log('ok - newest image found, drives listed (too-small one disabled), confirm, download, check, write, verify, done');
  } finally {
    await app.close();
    server.close();
  }
  assert.deepEqual(errors, []);
  console.log('mortar QA passed');
})().catch((e) => { console.error(e); process.exit(1); });
