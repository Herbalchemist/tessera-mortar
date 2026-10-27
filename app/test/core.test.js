'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { pickImages, parseSha } = require('../lib/releases');
const { resumePoint, downloadParts, sha256File } = require('../lib/download');
const { parseLsblk, parseGetDisk } = require('../lib/drives');
const writer = require('../lib/writer');

const asset = (name, size = 10) => ({ name, size, browser_download_url: `https://x/${name}` });

test('picks the newest build and its ISOs', () => {
  const p = (f, n, size = 10) => asset(`${f}.part${String(n).padStart(2, '0')}`, size);
  const imgs = pickImages([
    { tag_name: 'usb-old', published_at: '2026-10-01T00:00:00Z', assets: [p('Tessera-Live.iso', 0), asset('Tessera-Live.iso.sha256')] },
    { tag_name: 'usb-new', published_at: '2026-10-27T00:00:00Z', prerelease: true, assets: [
      ...Array.from({ length: 11 }, (_, i) => p('Tessera-Live.iso', i, i === 10 ? 1 : 10)), asset('Tessera-Live.iso.sha256'),
      p('Tessera-Live-nvidia.iso', 0, 7), p('Tessera-Live-nvidia.iso', 1, 3), asset('Tessera-Live-nvidia.iso.sha256'),
      p('Tessera-Live-amd-intel.iso', 0), // no checksum: not usable
      p('Tessera-Live-nvidia-open.iso', 0), p('Tessera-Live-nvidia-open.iso', 2), asset('Tessera-Live-nvidia-open.iso.sha256'), // a gap
    ] },
    { tag_name: 'usb-empty', published_at: '2026-10-28T00:00:00Z', assets: [] },
    { tag_name: 'v1.0', published_at: '2026-10-30T00:00:00Z', assets: [p('Tessera-Live.iso', 0), asset('Tessera-Live.iso.sha256')] },
  ]);
  assert.deepStrictEqual(imgs.map((i) => i.tag), ['usb-new', 'usb-old']);
  assert.deepStrictEqual(Object.keys(imgs[0].flavors).sort(), ['all', 'nvidia']);
  assert.deepStrictEqual(imgs[0].flavors.all.parts.map((x) => x.name.slice(-2)), ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10'], 'numeric order');
  assert.strictEqual(imgs[0].flavors.all.size, 101);
  assert.strictEqual(imgs[0].flavors.nvidia.size, 10);
  assert.strictEqual(parseSha(`${'A'.repeat(64)}  Tessera-Live.iso\n`), 'a'.repeat(64));
  assert.strictEqual(parseSha('nonsense'), null);
});

test('this PC: graphics to build', () => {
  const g = require('../lib/gpu');
  assert.strictEqual(g.flavorFor([{ vendor: '10de', device: '1c81' }]), 'nvidia');
  assert.strictEqual(g.flavorFor([{ vendor: '10de', device: '2684' }]), 'nvidia-open');
  assert.strictEqual(g.flavorFor([{ vendor: '8086', device: '9a49' }, { vendor: '10de', device: '25a2' }]), 'nvidia-open');
  assert.strictEqual(g.flavorFor([{ vendor: '1002', device: '73bf' }]), 'amd-intel');
  assert.strictEqual(g.flavorFor([{ vendor: '10de', device: '1187' }]), 'amd-intel');
  assert.strictEqual(g.flavorFor([]), null);
  const w = g.parseWindows(JSON.stringify([{ Name: 'NVIDIA GeForce GTX 1050', PNPDeviceID: 'PCI\\VEN_10DE&DEV_1C81&SUBSYS_1' }, { Name: 'Microsoft Basic Display Adapter', PNPDeviceID: 'ROOT\\BasicDisplay' }]));
  assert.deepStrictEqual(w, [{ vendor: '10de', device: '1c81', name: 'NVIDIA GeForce GTX 1050' }]);
});

test('resume point', () => {
  const parts = [{ size: 10 }, { size: 10 }, { size: 5 }];
  assert.deepStrictEqual(resumePoint(parts, 0), { index: 0, offset: 0 });
  assert.deepStrictEqual(resumePoint(parts, 13), { index: 1, offset: 3 });
  assert.deepStrictEqual(resumePoint(parts, 20), { index: 2, offset: 0 });
  assert.deepStrictEqual(resumePoint(parts, 25), { index: 3, offset: 0 });
});

test('Linux drives: USB and removable only, never the system disk', () => {
  const json = JSON.stringify({ blockdevices: [
    { name: 'nvme0n1', path: '/dev/nvme0n1', size: 1e12, model: 'Samsung', tran: 'nvme', rm: false, hotplug: false, type: 'disk', ro: false, mountpoints: [null], children: [{ mountpoints: ['/boot/efi'] }, { mountpoints: ['/', '/home'] }] },
    { name: 'sda', path: '/dev/sda', size: 32e9, vendor: 'SanDisk ', model: 'Ultra', tran: 'usb', rm: true, hotplug: true, type: 'disk', ro: false, mountpoints: [null], children: [{ mountpoints: ['/run/media/me/STICK'] }] },
    { name: 'sdb', path: '/dev/sdb', size: 2e12, model: 'External HDD', tran: 'usb', rm: false, hotplug: true, type: 'disk', ro: false, mountpoints: [null], children: [{ mountpoints: ['/'] }] },
    { name: 'sr0', path: '/dev/sr0', size: 1e9, tran: 'usb', rm: true, type: 'rom' },
    { name: 'loop0', path: '/dev/loop0', size: 1e9, rm: true, type: 'disk' },
  ] });
  const d = parseLsblk(json);
  assert.deepStrictEqual(d.map((x) => x.id), ['/dev/sda']);
  assert.strictEqual(d[0].name, 'SanDisk Ultra');
  assert.deepStrictEqual(d[0].mounts, ['/run/media/me/STICK']);
});

test('Windows drives: USB only, never boot or system', () => {
  const json = JSON.stringify([
    { Number: 0, FriendlyName: 'Samsung SSD', Size: 1e12, BusType: 'NVMe', IsBoot: true, IsSystem: true },
    { Number: 2, FriendlyName: 'SanDisk Ultra', Size: 32e9, BusType: 'USB', IsBoot: false, IsSystem: false },
    { Number: 3, FriendlyName: 'Weird', Size: 32e9, BusType: 'USB', IsBoot: true, IsSystem: false },
  ]);
  assert.deepStrictEqual(parseGetDisk(json).map((x) => x.id), ['\\\\.\\PhysicalDrive2']);
  assert.strictEqual(parseGetDisk(JSON.stringify({ Number: 1, FriendlyName: 'One', Size: 8e9, BusType: 'USB' })).length, 1, 'a single disk comes as an object');
});

test('download (with an interruption and resume), check, and write to a target file', { skip: process.platform === 'win32' }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mortar-'));
  const data = crypto.randomBytes(3 * 1024 * 1024 + 123);
  const sizes = [1024 * 1024, 1024 * 1024, data.length - 2 * 1024 * 1024];
  let cut = true;
  const server = http.createServer((req, res) => {
    const i = Number(req.url.match(/part(\d+)/)[1]);
    const start = sizes.slice(0, i).reduce((a, b) => a + b, 0);
    const part = data.subarray(start, start + sizes[i]);
    const m = /bytes=(\d+)-/.exec(req.headers.range || '');
    const from = m ? Number(m[1]) : 0;
    res.writeHead(m ? 206 : 200, { 'Content-Length': part.length - from });
    if (i === 1 && cut && !m) { cut = false; res.write(part.subarray(0, 1000)); return setTimeout(() => res.destroy(), 20); }
    res.end(part.subarray(from));
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}`;
  const image = { size: data.length, parts: sizes.map((size, i) => ({ name: `part0${i}`, size, url: `${base}/part0${i}` })) };
  const dest = path.join(dir, 'Tessera-Live.iso');
  let last = null;
  await downloadParts(image, dest, { onProgress: (p) => { last = p; } });
  server.close();
  assert.ok(data.equals(fs.readFileSync(dest)), 'joined file matches');
  assert.strictEqual(last.done, data.length);
  const sha = crypto.createHash('sha256').update(data).digest('hex');
  assert.strictEqual(await sha256File(dest), sha);
  if (!(process.getuid && process.getuid() === 0)) return;
  const target = path.join(dir, 'usb.bin');
  fs.writeFileSync(target, Buffer.alloc(8 * 1024 * 1024));
  process.env.MORTAR_TEST_TARGET = target;
  const phases = new Set();
  const r = await writer.write(dest, { id: target }, sha, { onProgress: (p) => phases.add(p.phase) });
  assert.strictEqual(r.sha, sha);
  assert.ok(phases.has('write') && phases.has('verify'));
  await assert.rejects(writer.write(dest, { id: target }, 'f'.repeat(64)), /doesn't read back the same/);
});
