'use strict';
// Mortar's window: pick an image and a USB drive, then make the USB and follow along.
const $ = (id) => document.getElementById(id);
const gb = (n) => `${(n / 1e9).toFixed(1)} GB`;
const MIN = 30e9; // a "32 GB" drive is a little under 32e9 bytes
const state = { newest: null, file: null, drives: [], drive: null, src: 'release', busy: false };

function dateOf(s) { try { return new Date(s).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); } catch { return ''; } }
function needed() { return state.src === 'file' ? (state.file ? state.file.size : 0) : state.newest && state.newest.ok ? state.newest.image.size : 0; }

async function loadNewest() {
  const r = await window.mortar.newest();
  state.newest = r;
  const el = $('imageInfo');
  if (!r.ok) {
    el.textContent = `Couldn't check GitHub: ${r.error} You can still use an image file you already have.`;
    el.className = 'bad';
  } else {
    const have = r.downloaded ? 'Already downloaded.' : r.partial ? `Partly downloaded (${gb(r.partial)}); it carries on where it stopped.` : `A ${gb(r.image.size)} download.`;
    el.innerHTML = '';
    const b = document.createElement('b');
    b.textContent = `Tessera USB, built ${dateOf(r.image.published)}`;
    el.append(b, document.createTextNode(` · ${have} Installs offline, with every graphics build on it.`));
    el.className = 'muted';
    $('ver').textContent = r.image.tag;
  }
  refresh();
}

const driveIcon = () => '<svg class="ico" viewBox="0 0 30 30"><rect x="9" y="3" width="12" height="7" rx="1.5"/><rect x="6" y="10" width="18" height="17" rx="3"/><path d="M13 6h1M16 6h1"/></svg>';
async function loadDrives() {
  if (state.busy) return;
  const r = await window.mortar.drives();
  const list = r.drives || [];
  const sig = JSON.stringify(list.map((d) => [d.id, d.size, d.name]));
  if (sig === state.sig) return;
  state.sig = sig;
  state.drives = list;
  if (state.drive && !list.some((d) => d.id === state.drive)) state.drive = null;
  if (!state.drive && list.length === 1 && list[0].size >= MIN) state.drive = list[0].id;
  renderDrives();
  refresh();
}
function renderDrives() {
  const box = $('drives');
  box.replaceChildren();
  if (!state.drives.length) {
    const e = document.createElement('div');
    e.className = 'empty';
    e.textContent = 'No USB drive found yet. Plug one in; it shows up here by itself.';
    box.append(e);
    return;
  }
  for (const d of state.drives) {
    const b = document.createElement('button');
    b.className = 'drive' + (state.drive === d.id ? ' sel' : '');
    b.dataset.id = d.id;
    const small = d.size < Math.max(MIN, needed());
    b.disabled = small;
    b.innerHTML = driveIcon();
    const t = document.createElement('div');
    const nm = document.createElement('div'); nm.className = 'nm'; nm.textContent = d.name;
    const sub = document.createElement('div'); sub.className = 'sub';
    sub.textContent = [gb(d.size), d.bus, small ? 'too small' : d.mounts && d.mounts.length ? `in use at ${d.mounts[0]}` : ''].filter(Boolean).join(' · ');
    t.append(nm, sub);
    b.append(t);
    b.addEventListener('click', () => { state.drive = d.id; renderDrives(); refresh(); });
    box.append(b);
  }
}
function refresh() {
  const hasImage = state.src === 'file' ? Boolean(state.file) : Boolean(state.newest && state.newest.ok);
  const d = state.drives.find((x) => x.id === state.drive);
  $('go').disabled = !(hasImage && d);
  $('goInfo').textContent = !hasImage ? 'Choose an image first.' : !d ? 'Choose a USB drive.' : `Ready to write to ${d.name} (${gb(d.size)}).`;
}

document.querySelectorAll('input[name=src]').forEach((r) => r.addEventListener('change', async () => {
  state.src = r.value;
  if (state.src === 'file' && !state.file) {
    const f = await window.mortar.chooseIso();
    if (!f) { state.src = 'release'; document.querySelector('input[value=release]').checked = true; }
    else state.file = f;
  }
  $('fileInfo').hidden = state.src !== 'file' || !state.file;
  if (state.file) $('fileInfo').textContent = `${state.file.name} · ${gb(state.file.size)}`;
  renderDrives();
  refresh();
}));
$('fileInfo').addEventListener('click', async () => { const f = await window.mortar.chooseIso(); if (f) { state.file = f; $('fileInfo').textContent = `${f.name} · ${gb(f.size)}`; refresh(); } });

// ---- making it
const STEPS = { release: ['download', 'check', 'write', 'verify'], file: ['check', 'write', 'verify'] };
const NAMES = { download: 'Download Tessera', check: 'Check the download', write: 'Write to the USB drive', verify: 'Check the USB drive' };
let t0 = 0;
let phaseStart = {};
function fmtTime(s) { s = Math.max(0, Math.round(s)); return s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min` : s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`; }
function showSteps(order, current, p) {
  const ol = $('steps');
  ol.replaceChildren();
  const at = order.indexOf(current);
  order.forEach((k, i) => {
    const li = document.createElement('li');
    li.textContent = NAMES[k];
    li.className = i < at ? 'done' : i === at ? 'now' : '';
    if (i === at && p && p.total) {
      const d = document.createElement('span');
      d.className = 'd';
      const pct = Math.min(100, Math.floor((p.done / p.total) * 100));
      const el = (Date.now() - (phaseStart[k] || Date.now())) / 1000;
      const rate = p.rate || (el > 2 ? p.done / el : 0);
      const left = rate > 0 ? (p.total - p.done) / rate : 0;
      d.textContent = `${pct}% · ${gb(p.done)} of ${gb(p.total)}${left > 3 ? ` · about ${fmtTime(left)} left` : ''}`;
      li.append(d);
    }
    ol.append(li);
  });
  const overall = order.length ? ((at + (p && p.total ? p.done / p.total : 0)) / order.length) * 100 : 0;
  $('barFill').style.width = `${Math.max(0, Math.min(100, overall)).toFixed(1)}%`;
}
window.mortar.onProgress((p) => {
  if (!state.busy) return;
  if (!phaseStart[p.phase]) phaseStart[p.phase] = Date.now();
  showSteps(STEPS[state.src], p.phase, p);
  $('workLine').textContent = p.phase === 'write' && window.mortar.platform === 'linux' && p.done === 0 ? 'Your computer may ask for your password, to let Mortar write the drive.' : 'You can keep using your computer. Leave the USB drive plugged in.';
});

function ask(text) {
  return new Promise((resolve) => {
    $('confirmText').textContent = text;
    $('confirm').hidden = false;
    $('confirmNo').focus();
    const done = (v) => { $('confirm').hidden = true; $('confirmYes').onclick = null; $('confirmNo').onclick = null; resolve(v); };
    $('confirmYes').onclick = () => done(true);
    $('confirmNo').onclick = () => done(false);
  });
}

$('go').addEventListener('click', async () => {
  const d = state.drives.find((x) => x.id === state.drive);
  if (!d) return;
  if (!(await ask(`Everything on ${d.name} (${gb(d.size)}) will be erased and replaced with the Tessera installer.`))) return;
  state.busy = true;
  t0 = Date.now();
  phaseStart = {};
  $('setup').hidden = true; $('working').hidden = false; $('finished').hidden = true;
  $('workTitle').textContent = 'Making your Tessera USB';
  showSteps(STEPS[state.src], STEPS[state.src][0], null);
  $('workLine').textContent = 'Starting…';
  const r = await window.mortar.make({ driveId: d.id, source: state.src === 'file' ? { type: 'file', path: state.file.path } : { type: 'release' } });
  state.busy = false;
  $('working').hidden = true; $('finished').hidden = false;
  const body = $('doneBody');
  body.replaceChildren();
  if (r.ok) {
    $('doneTitle').textContent = 'Your Tessera USB is ready';
    $('doneTitle').className = 'ok';
    body.innerHTML = '<p>It took ' + fmtTime((Date.now() - t0) / 1000) + '. To install Tessera:</p><ol>'
      + '<li>Plug the USB into the PC that gets Tessera, and start it from the USB. The key for the boot menu is usually F12, F11, F8 or Esc.</li>'
      + '<li>Pick <b>Try or install Tessera</b>. If the screen stays black, restart and pick <b>safe graphics</b> or <b>desktop mode</b>.</li>'
      + '<li>Follow <b>Install Tessera</b>. It works with a controller, a keyboard or a mouse, and needs no internet.</li></ol>'
      + '<p class="muted">The disk you install to is erased. Windows may say the USB needs formatting: choose Cancel, the drive is fine.</p>';
  } else {
    $('doneTitle').textContent = "The USB isn't ready";
    $('doneTitle').className = 'bad';
    const p = document.createElement('p');
    p.textContent = r.error;
    body.append(p);
  }
});
$('stop').addEventListener('click', async () => { if (await ask('Stop now? The download is kept for next time, but the USB drive will be incomplete.')) window.mortar.cancel(); });
$('again').addEventListener('click', () => { $('finished').hidden = true; $('setup').hidden = false; state.sig = ''; loadNewest(); loadDrives(); });
$('help').addEventListener('click', () => window.mortar.open('help'));
$('releasesLink').addEventListener('click', (e) => { e.preventDefault(); window.mortar.open('releases'); });
$('folderLink').addEventListener('click', (e) => { e.preventDefault(); window.mortar.open('folder'); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('confirm').hidden) $('confirmNo').click(); });

loadNewest();
loadDrives();
setInterval(loadDrives, 2500);
