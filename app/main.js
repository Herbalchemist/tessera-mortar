'use strict';
// Tessera Mortar: makes a Tessera USB installer. Downloads the newest Tessera USB image from GitHub
// (or uses an ISO you already have), checks it, writes it to a USB drive and checks the drive.
const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const releases = require('./lib/releases');
const { downloadParts, sha256File } = require('./lib/download');
const drives = require('./lib/drives');
const writer = require('./lib/writer');

let win = null;
let job = null; // { controller }
const send = (ch, payload) => { if (win && !win.isDestroyed()) win.webContents.send(ch, payload); };
const downloadDir = () => process.env.MORTAR_DOWNLOAD_DIR || path.join(app.getPath('downloads'), 'Tessera Mortar');
const isoFor = (img) => path.join(downloadDir(), `Tessera-Live-${img.tag}.iso`);
const freeSpace = (dir) => { try { const s = fs.statfsSync(dir); return s.bavail * s.bsize; } catch { return Infinity; } };
let newestCache = null;

async function listDrives() {
  if (process.env.MORTAR_FAKE_DRIVES) return JSON.parse(process.env.MORTAR_FAKE_DRIVES);
  return drives.list();
}

ipcMain.handle('newest', async () => {
  try {
    const img = await releases.newest();
    newestCache = img;
    const iso = isoFor(img);
    const have = fs.existsSync(iso) && fs.statSync(iso).size === img.size;
    const partial = fs.existsSync(`${iso}.partial`) ? fs.statSync(`${iso}.partial`).size : 0;
    return { ok: true, image: { tag: img.tag, title: img.title, published: img.published, size: img.size, parts: img.parts.length, page: img.page }, downloaded: have, partial, folder: downloadDir() };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});
ipcMain.handle('drives', async () => {
  try { return { ok: true, drives: await listDrives() }; } catch (e) { return { ok: false, error: e.message, drives: [] }; }
});
ipcMain.handle('chooseIso', async () => {
  const r = await dialog.showOpenDialog(win, { title: 'Choose a Tessera USB image', filters: [{ name: 'Disk images', extensions: ['iso', 'img'] }], properties: ['openFile'] });
  if (r.canceled || !r.filePaths[0]) return null;
  const p = r.filePaths[0];
  return { path: p, name: path.basename(p), size: fs.statSync(p).size };
});
ipcMain.handle('open', (_e, what) => {
  if (what === 'folder') return shell.openPath(downloadDir());
  if (what === 'help') return shell.openExternal('https://github.com/Herbalchemist/tessera#install');
  if (what === 'releases') return shell.openExternal(`https://github.com/${releases.REPO}/releases`);
  return null;
});
ipcMain.handle('cancel', () => { if (job) job.controller.abort(); return true; });

// The whole job: [download → check] → write → check the USB.
ipcMain.handle('make', async (_e, req) => {
  if (job) return { ok: false, error: 'Already making a USB.' };
  const controller = new AbortController();
  job = { controller };
  const signal = controller.signal;
  const progress = (p) => send('progress', p);
  try {
    const list = await listDrives();
    const drive = list.find((d) => d.id === req.driveId);
    if (!drive) throw new Error('That USB drive is gone. Plug it back in and choose it again.');
    let image;
    let expected = null;
    if (req.source && req.source.type === 'file') {
      image = req.source.path;
      if (!fs.existsSync(image)) throw new Error("The image file isn't there any more.");
      const shaFile = `${image}.sha256`;
      if (fs.existsSync(shaFile)) expected = releases.parseSha(fs.readFileSync(shaFile, 'utf8'));
      if (expected) {
        progress({ phase: 'check', done: 0, total: fs.statSync(image).size });
        const got = await sha256File(image, { onProgress: progress, signal });
        if (got !== expected) throw new Error("The image file doesn't match its checksum file. It may be damaged; download it again.");
      }
    } else {
      const img = newestCache || (await releases.newest());
      image = isoFor(img);
      expected = img.sha256;
      fs.mkdirSync(downloadDir(), { recursive: true });
      const need = img.size - (fs.existsSync(`${image}.partial`) ? fs.statSync(`${image}.partial`).size : 0);
      if (!(fs.existsSync(image) && fs.statSync(image).size === img.size) && freeSpace(downloadDir()) < need + 256 * 1024 * 1024) {
        throw new Error(`Not enough free space for the download: it needs ${(need / 1e9).toFixed(1)} GB in ${downloadDir()}.`);
      }
      await downloadParts(img, image, { onProgress: progress, signal });
      progress({ phase: 'check', done: 0, total: img.size });
      const got = await sha256File(image, { onProgress: progress, signal });
      if (got !== expected) {
        fs.renameSync(image, `${image}.bad`);
        throw new Error('The download is damaged (its checksum doesn\'t match). Try again to download it afresh.');
      }
    }
    const size = fs.statSync(image).size;
    if (drive.size && drive.size < size) throw new Error(`That drive is too small: the image needs ${(size / 1e9).toFixed(1)} GB.`);
    progress({ phase: 'write', done: 0, total: size });
    const r = await writer.write(image, drive, expected, { onProgress: progress, signal });
    if (!expected) {
      // An image without a checksum file: compare the drive with the file itself.
      const fileSha = await sha256File(image, { onProgress: (p) => progress({ ...p, phase: 'verify' }), signal });
      if (fileSha !== r.sha) throw new Error("The drive doesn't read back the same as the image. The USB drive may be faulty; try another one.");
    }
    return { ok: true, drive: drive.name };
  } catch (e) {
    return { ok: false, error: signal.aborted ? 'Stopped. The USB drive is incomplete; make it again before using it.' : e.message };
  } finally {
    job = null;
  }
});

function createWindow() {
  win = new BrowserWindow({
    width: 940, height: 720, minWidth: 720, minHeight: 600, title: 'Tessera Mortar', backgroundColor: '#120f1c', show: false,
    autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  win.removeMenu();
  win.once('ready-to-show', () => win.show());
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (e) => e.preventDefault());
  win.loadFile(path.join(__dirname, 'index.html'));
  win.on('close', (e) => {
    if (!job) return;
    const c = dialog.showMessageBoxSync(win, { type: 'warning', buttons: ['Keep going', 'Stop and quit'], defaultId: 0, cancelId: 0, message: 'Mortar is still making the USB.', detail: 'If you quit now, the USB drive will be incomplete.' });
    if (c === 0) e.preventDefault(); else job.controller.abort();
  });
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());
