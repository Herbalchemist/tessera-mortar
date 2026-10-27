'use strict';
// Writes the image to the chosen drive and reads it back to check it.
// Linux: a small script run as root through pkexec (the usual password prompt).
// Windows: Mortar runs as administrator; the drive's partitions are cleared with diskpart (so
// Windows lets go of them) and the image goes straight to \\.\PhysicalDriveN.
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { run } = require('./drives');

const CHUNK = 4 << 20; // 4 MiB, a multiple of every sector size
const ALIGN = 4096;

function writeLinux(image, drive, { onProgress = () => {}, signal } = {}) {
  return new Promise((resolve, reject) => {
    // pkexec runs as root, which can't read inside a running AppImage. The script's text goes on the
    // command line itself (sh -c) rather than into a file: a file in /tmp could be swapped by someone
    // else between writing it and root running it, and the command line can't be changed once
    // pkexec has asked for the password.
    const script = fs.readFileSync(path.join(__dirname, '..', 'bin', 'mortar-write-linux.sh'), 'utf8');
    const asRoot = process.getuid && process.getuid() === 0;
    const args = ['/bin/sh', '-c', script, 'mortar-write', image, drive.id, ...(Number.isInteger(drive.size) && drive.size > 0 ? [String(drive.size)] : [])];
    const cmd = asRoot || process.env.MORTAR_NO_PKEXEC === '1' ? args : ['pkexec', ...args];
    const total = fs.statSync(image).size;
    const child = spawn(cmd[0], cmd.slice(1), { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env } });
    let phase = 'write';
    let sha = null;
    let error = '';
    let buf = '';
    if (signal) signal.addEventListener('abort', () => child.kill('SIGTERM'), { once: true });
    child.stdout.on('data', (d) => {
      buf += d;
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const l of lines) {
        if (l.startsWith('PHASE ')) phase = l.slice(6).trim();
        else if (l.startsWith('BYTES ')) onProgress({ phase, done: Math.min(total, Number(l.slice(6)) || 0), total });
        else if (l.startsWith('SHA ')) sha = l.slice(4).trim();
        else if (l.startsWith('ERROR ')) error = l.slice(6).trim();
      }
    });
    child.stderr.on('data', (d) => { if (!error) error = String(d).trim().split('\n').pop(); });
    child.on('error', (e) => reject(new Error(e.code === 'ENOENT' ? 'pkexec is missing, so Mortar can\'t ask for permission to write the drive.' : e.message)));
    child.on('close', (code) => {
      if (signal && signal.aborted) return reject(new Error('Cancelled.'));
      if (code === 126 || code === 127) return reject(new Error('Permission to write the drive was refused.'));
      if (code !== 0 || !sha) return reject(new Error(error || `Writing the drive failed (${code}).`));
      resolve({ sha });
    });
  });
}

async function diskpartClean(number) {
  const file = path.join(os.tmpdir(), `mortar-diskpart-${process.pid}.txt`);
  fs.writeFileSync(file, `select disk ${number}\nattributes disk clear readonly noerr\nonline disk noerr\nclean\nrescan\n`);
  const r = await run('diskpart.exe', ['/s', file], { timeout: 120000 });
  try { fs.rmSync(file, { force: true }); } catch { /* fine */ }
  if (!/succeeded in cleaning|erfolgreich|correctement|exitosamente/i.test(r.out) && !r.ok) throw new Error(`Windows couldn't clear the drive. ${r.out.trim().split('\n').slice(-2).join(' ')}`);
}

async function writeWindows(image, drive, { onProgress = () => {}, signal } = {}) {
  if (!Number.isInteger(drive.number)) throw new Error('Unknown drive.');
  await diskpartClean(drive.number);
  const total = fs.statSync(image).size;
  const dev = `\\\\.\\PhysicalDrive${drive.number}`;
  let out;
  try { out = await fs.promises.open(dev, 'r+'); } catch (e) {
    throw new Error(e.code === 'EPERM' || e.code === 'EACCES' ? 'Windows refused access to the drive. Run Mortar as administrator.' : `Couldn't open the drive (${e.code || e.message}).`);
  }
  const inp = await fs.promises.open(image, 'r');
  const buf = Buffer.alloc(CHUNK);
  try {
    let pos = 0;
    while (pos < total) {
      if (signal && signal.aborted) throw new Error('Cancelled.');
      const { bytesRead } = await inp.read(buf, 0, Math.min(CHUNK, total - pos), pos);
      if (!bytesRead) throw new Error('The image file ended early.');
      let len = bytesRead;
      if (len % ALIGN) { const padded = Math.ceil(len / ALIGN) * ALIGN; buf.fill(0, len, padded); len = padded; }
      await out.write(buf, 0, len, pos);
      pos += bytesRead;
      onProgress({ phase: 'write', done: pos, total });
    }
    await out.sync();
  } finally {
    await out.close();
    await inp.close();
  }
  // Read it back.
  const back = await fs.promises.open(dev, 'r');
  const h = crypto.createHash('sha256');
  try {
    let pos = 0;
    while (pos < total) {
      if (signal && signal.aborted) throw new Error('Cancelled.');
      const want = Math.ceil(Math.min(CHUNK, total - pos) / ALIGN) * ALIGN;
      const { bytesRead } = await back.read(buf, 0, want, pos);
      if (!bytesRead) throw new Error("Couldn't read the drive back.");
      const use = Math.min(bytesRead, total - pos);
      h.update(buf.subarray(0, use));
      pos += use;
      onProgress({ phase: 'verify', done: pos, total });
    }
  } finally {
    await back.close();
  }
  return { sha: h.digest('hex') };
}

async function write(image, drive, expectedSha, opts = {}) {
  const r = process.platform === 'win32' ? await writeWindows(image, drive, opts) : await writeLinux(image, drive, opts);
  if (expectedSha && r.sha !== expectedSha) throw new Error("The drive doesn't read back the same as the image. The USB drive may be faulty; try another one.");
  return r;
}

module.exports = { write, writeLinux, writeWindows };
