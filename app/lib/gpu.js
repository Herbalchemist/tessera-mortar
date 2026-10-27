'use strict';
// Which Tessera build suits this computer's graphics, for "Create media for this PC". The rules
// match Tessera's own (launcher/gpu-match.js): NVIDIA GTX 16 / RTX (Turing, device id 0x1e00 and up)
// -> nvidia-open; GTX 900-1000 / Titan V (0x1300-0x1dff) -> nvidia; older NVIDIA, AMD, Intel -> amd-intel.
const fs = require('fs');
const path = require('path');
const { run } = require('./drives');

const VENDORS = { '1002': 'AMD', '1022': 'AMD', '8086': 'Intel', '10de': 'NVIDIA' };

function generation(device) {
  const d = parseInt(device, 16);
  if (!Number.isFinite(d)) return 'unknown';
  return d >= 0x1e00 ? 'open' : d >= 0x1300 ? 'legacy' : 'unsupported';
}

// Pure: [{ vendor, device }] (hex) -> flavor.
function flavorFor(gpus) {
  const nv = gpus.filter((g) => String(g.vendor).toLowerCase() === '10de').map((g) => generation(g.device));
  if (nv.includes('legacy')) return 'nvidia';
  if (nv.includes('open')) return 'nvidia-open';
  if (!gpus.length || nv.includes('unknown')) return null;
  return 'amd-intel';
}

// Pure: Win32_VideoController JSON -> [{ vendor, device, name }]
function parseWindows(json) {
  let list = [];
  try { list = JSON.parse(json); } catch { return []; }
  if (!Array.isArray(list)) list = list ? [list] : [];
  return list.map((c) => {
    const m = /VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})/i.exec(String(c.PNPDeviceID || ''));
    return m ? { vendor: m[1].toLowerCase(), device: m[2].toLowerCase(), name: String(c.Name || '').trim() } : null;
  }).filter(Boolean).filter((g) => VENDORS[g.vendor]); // skip virtual adapters (Microsoft Basic Display, remote desktop…)
}

function readLinux(dir = '/sys/bus/pci/devices') {
  const out = [];
  let names = [];
  try { names = fs.readdirSync(dir); } catch { return out; }
  for (const n of names) {
    const rd = (f) => { try { return fs.readFileSync(path.join(dir, n, f), 'utf8').trim().toLowerCase().replace(/^0x/, ''); } catch { return ''; } };
    if (rd('class').startsWith('03')) out.push({ vendor: rd('vendor'), device: rd('device'), name: '' });
  }
  return out;
}

async function detect() {
  if (process.env.MORTAR_FAKE_GPUS) return JSON.parse(process.env.MORTAR_FAKE_GPUS);
  if (process.platform === 'win32') {
    const r = await run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', 'Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID | ConvertTo-Json -Compress']);
    return parseWindows(r.out);
  }
  const gpus = readLinux();
  // names from lspci, when it's there
  for (const g of gpus) g.name = `${VENDORS[g.vendor] || 'Unknown'} graphics (${g.vendor}:${g.device})`;
  const r = await run('lspci', ['-mm', '-nn', '-d', '::0300']).catch(() => ({ out: '' }));
  for (const line of String(r.out || '').split('\n')) {
    const m = /"[^"]*" "([^"]*) \[([0-9a-f]{4})\]" "([^"]*) \[([0-9a-f]{4})\]"/i.exec(line);
    if (!m) continue;
    const g = gpus.find((x) => x.vendor === m[2].toLowerCase() && x.device === m[4].toLowerCase());
    if (g) g.name = `${m[1].replace(/ Corporation|, Inc\.| \[AMD\/ATI\]/g, '')} ${m[3]}`.trim();
  }
  return gpus;
}

module.exports = { detect, flavorFor, parseWindows, generation, VENDORS };
