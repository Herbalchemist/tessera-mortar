'use strict';
// Downloads the image's parts into one file, picking up where it left off if interrupted, then
// checks the whole file against the published SHA-256.
const fs = require('fs');
const crypto = require('crypto');
const { request } = require('./http');

// Pure: where a partly downloaded file stands. done = bytes already on disk.
function resumePoint(parts, done) {
  let at = 0;
  for (let i = 0; i < parts.length; i++) {
    if (done < at + parts[i].size) return { index: i, offset: done - at };
    at += parts[i].size;
  }
  return { index: parts.length, offset: 0 };
}

async function downloadParts(image, dest, { onProgress = () => {}, signal } = {}) {
  const partial = `${dest}.partial`;
  if (fs.existsSync(dest) && fs.statSync(dest).size === image.size) return dest; // already here
  let done = fs.existsSync(partial) ? fs.statSync(partial).size : 0;
  if (done > image.size) { fs.rmSync(partial); done = 0; }
  const start = resumePoint(image.parts, done);
  const out = fs.createWriteStream(partial, { flags: 'a' });
  const t0 = Date.now();
  const startDone = done;
  try {
    for (let i = start.index; i < image.parts.length; i++) {
      const p = image.parts[i];
      const offset = i === start.index ? start.offset : 0;
      let tries = 0;
      let got = offset;
      while (got < p.size) {
        try {
          const res = await request(p.url, { headers: got ? { Range: `bytes=${got}-` } : {}, signal });
          if (got && res.statusCode !== 206) { res.resume(); throw new Error(`The server didn't resume the download (${res.statusCode}).`); }
          if (!got && res.statusCode !== 200) { res.resume(); throw new Error(`Download failed (${res.statusCode}).`); }
          for await (const chunk of res) {
            const room = p.size - got;
            const c = chunk.length > room ? chunk.subarray(0, room) : chunk;
            if (!out.write(c)) await new Promise((r) => out.once('drain', r));
            got += c.length;
            done += c.length;
            const secs = (Date.now() - t0) / 1000;
            onProgress({ phase: 'download', done, total: image.size, rate: secs > 1 ? (done - startDone) / secs : 0 });
          }
          if (got < p.size) throw new Error('The connection closed early.');
        } catch (e) {
          if (signal && signal.aborted) throw new Error('Cancelled.');
          if (++tries >= 5) throw e;
          await new Promise((r) => setTimeout(r, 2000 * tries));
        }
      }
    }
  } finally {
    await new Promise((r) => out.end(r));
  }
  fs.renameSync(partial, dest);
  return dest;
}

function sha256File(file, { onProgress = () => {}, signal, size } = {}) {
  return new Promise((resolve, reject) => {
    const total = size || fs.statSync(file).size;
    const h = crypto.createHash('sha256');
    let done = 0;
    const s = fs.createReadStream(file, { highWaterMark: 4 << 20 });
    if (signal) signal.addEventListener('abort', () => s.destroy(new Error('Cancelled.')), { once: true });
    s.on('data', (c) => { h.update(c); done += c.length; onProgress({ phase: 'check', done, total }); });
    s.on('error', reject);
    s.on('end', () => resolve(h.digest('hex')));
  });
}

module.exports = { resumePoint, downloadParts, sha256File };
