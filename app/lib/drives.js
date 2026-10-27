'use strict';
// Lists the drives Mortar may write to: removable / USB drives only, never the disk the computer
// runs from. Linux uses lsblk, Windows uses PowerShell's Get-Disk.
const { execFile } = require('child_process');

const run = (cmd, args, opts = {}) => new Promise((resolve) => {
  execFile(cmd, args, { encoding: 'utf8', timeout: 20000, windowsHide: true, maxBuffer: 8 << 20, ...opts }, (err, stdout, stderr) => resolve({ ok: !err, out: stdout || '', err: stderr || (err && err.message) || '' }));
});
const truthy = (v) => v === true || v === 1 || v === '1' || v === 'true';

// Pure: lsblk -J output -> drives. A disk counts if it's USB, removable or hot-pluggable, and none
// of its partitions is mounted at /, /boot, /usr or /home (the running system).
function parseLsblk(json) {
  let devs = [];
  try { devs = JSON.parse(json).blockdevices || []; } catch { return []; }
  const SYSTEM = /^\/(boot(\/efi)?|usr|home|var|sysroot)?$/;
  const mounts = (d) => [...(d.mountpoints || []), d.mountpoint, ...(d.children || []).flatMap(mounts)].filter(Boolean);
  const out = [];
  for (const d of devs) {
    if (d.type !== 'disk' || truthy(d.ro)) continue;
    const path = d.path || `/dev/${d.name}`;
    if (/^\/dev\/(loop|zram|ram|sr|fd|dm-|md)/.test(path)) continue;
    const size = Number(d.size) || 0;
    if (size <= 0) continue;
    const usb = String(d.tran || '').toLowerCase() === 'usb';
    if (!(usb || truthy(d.rm) || truthy(d.hotplug))) continue;
    const m = mounts(d);
    if (m.some((x) => SYSTEM.test(x))) continue;
    out.push({ id: path, name: [d.vendor, d.model].map((s) => String(s || '').trim()).filter(Boolean).join(' ') || 'USB drive', size, mounts: m, bus: usb ? 'USB' : 'Removable' });
  }
  return out;
}

// Pure: Get-Disk JSON -> drives (USB only, never the boot or system disk).
function parseGetDisk(json, anyBus = false) {
  let list = [];
  try { list = JSON.parse(json); } catch { return []; }
  if (!Array.isArray(list)) list = list ? [list] : [];
  return list
    .filter((d) => d && !truthy(d.IsBoot) && !truthy(d.IsSystem) && Number(d.Size) > 0 && (anyBus || String(d.BusType) === 'USB' || d.BusType === 7))
    .map((d) => ({ id: `\\\\.\\PhysicalDrive${Number(d.Number)}`, number: Number(d.Number), name: String(d.FriendlyName || 'USB drive').trim(), size: Number(d.Size), mounts: [], bus: String(d.BusType) }));
}

async function list() {
  if (process.platform === 'win32') {
    const ps = "Get-Disk | Select-Object Number,FriendlyName,Size,BusType,IsBoot,IsSystem | ConvertTo-Json -Compress";
    const r = await run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps]);
    return parseGetDisk(r.out, process.env.MORTAR_ANY_DISK === '1');
  }
  const r = await run('lsblk', ['-J', '-b', '-o', 'NAME,PATH,SIZE,MODEL,VENDOR,TRAN,RM,HOTPLUG,TYPE,RO,MOUNTPOINTS']);
  return parseLsblk(r.out);
}

module.exports = { list, parseLsblk, parseGetDisk, run };
