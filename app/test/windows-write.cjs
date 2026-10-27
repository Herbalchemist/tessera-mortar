// Windows CI check: writes an image to a real (virtual) disk the way Mortar does for a USB drive,
// and reads it back.  node test/windows-write.cjs DISK_NUMBER
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { writeWindows } = require('../lib/writer');
const drives = require('../lib/drives');

(async () => {
  const number = Number(process.argv[2]);
  const img = path.join(os.tmpdir(), 'mortar-test.iso');
  const data = crypto.randomBytes(40 * 1024 * 1024 + 2048); // not a multiple of 4 KiB, like a real ISO might be
  fs.writeFileSync(img, data);
  const want = crypto.createHash('sha256').update(data).digest('hex');
  process.env.MORTAR_ANY_DISK = '1';
  const list = await drives.list();
  console.log('drives:', JSON.stringify(list));
  const d = list.find((x) => x.number === number);
  if (!d) throw new Error(`disk ${number} not listed`);
  let last = null;
  const r = await writeWindows(img, d, { onProgress: (p) => { last = p; } });
  console.log('last progress', JSON.stringify(last));
  if (r.sha !== want) throw new Error(`read back ${r.sha}, wanted ${want}`);
  console.log('::notice title=Windows write::wrote and read back 40 MB on PhysicalDrive' + number);
})().catch((e) => { console.log(`::error title=Windows write::${e.message}`); process.exit(1); });
