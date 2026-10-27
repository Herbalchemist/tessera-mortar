'use strict';
// Mortar's window. First a choice (quick, this PC, or customized), then the drive, then the work.
const $ = (id) => document.getElementById(id);
const gb = (n) => `${(n / 1e9).toFixed(1)} GB`;
const FLAVOR_NAMES = { all: 'Every graphics build (any PC)', 'amd-intel': 'AMD / Intel', nvidia: 'NVIDIA, GTX 900–1000', 'nvidia-open': 'NVIDIA, GTX 16 / RTX' };
// The usual size printed on a USB drive that holds this many bytes (drives hold a little less than they say).
const usbFor = (bytes) => [8, 16, 32, 64, 128].find((g) => g * 1e9 * 0.93 >= bytes) || 256;
const state = { newest: null, gpu: null, mode: null, flavor: 'all', src: 'release', file: null, drives: [], drive: null, busy: false };

function dateOf(s) { try { return new Date(s).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); } catch { return ''; } }
const flavorsAvail = () => (state.newest && state.newest.ok ? state.newest.flavors : {});
function needed() {
  if (state.src === 'file') return state.file ? state.file.size : 0;
  const f = flavorsAvail()[state.flavor];
  return f ? f.size : 0;
}

// ---- the first screen
async function loadNewest() {
  const r = await window.mortar.newest();
  state.newest = r;
  const el = $('imageInfo');
  if (!r.ok) {
    el.textContent = `Couldn't check GitHub: ${r.error} "Customize my install" can still use an image file you already have.`;
    el.className = 'bad center';
  } else {
    el.textContent = `Newest Tessera: built ${dateOf(r.image.published)}. Every option installs with no internet needed.`;
    el.className = 'muted center';
    $('ver').textContent = r.image.tag;
  }
  paintChoices();
}
async function loadGpu() {
  state.gpu = await window.mortar.gpu();
  paintChoices();
}
function paintChoices() {
  const fl = flavorsAvail();
  const ok = state.newest && state.newest.ok;
  $('optQuick').disabled = !ok || !fl.all;
  if (fl.all) $('badgeQuick').textContent = `${usbFor(fl.all.size)} GB USB`;
  const g = state.gpu;
  const mine = g && g.flavor;
  if (!g) $('thisInfo').textContent = "Looking at this PC's graphics…";
  else if (!mine) $('thisInfo').textContent = "Couldn't tell which graphics this PC has. Use Quick install, or pick a build under Customize.";
  else if (ok && !fl[mine]) $('thisInfo').textContent = `This PC has ${g.cards.join(' + ')} (${FLAVOR_NAMES[mine]}). USBs for one PC aren't in the newest build yet; use Quick install for now.`;
  else $('thisInfo').textContent = `This PC has ${g.cards.join(' + ') || 'its graphics'}, so only the ${FLAVOR_NAMES[mine]} build goes on the USB. For this PC, or one with the same kind of graphics.`;
  $('optThis').disabled = !ok || !mine || !fl[mine];
  if (mine && fl[mine]) $('badgeThis').textContent = `${usbFor(fl[mine].size)} GB USB`;
}
document.querySelectorAll('.option').forEach((b) => b.addEventListener('click', () => choose(b.dataset.mode)));

function choose(mode) {
  state.mode = mode;
  state.src = 'release';
  state.flavor = mode === 'thispc' ? state.gpu.flavor : 'all';
  if (mode === 'custom' && !flavorsAvail().all) state.flavor = Object.keys(flavorsAvail())[0] || 'all';
  $('choose').hidden = true; $('setup').hidden = false;
  paintWhat();
  renderDrives();
  refresh();
}
$('back').addEventListener('click', (e) => { e.preventDefault(); $('setup').hidden = true; $('choose').hidden = false; });

function paintWhat() {
  const fl = flavorsAvail();
  const f = fl[state.flavor];
  const have = (x) => (x && x.downloaded ? ' Already downloaded.' : x && x.partial ? ` Partly downloaded; it carries on where it stopped.` : '');
  $('flavors').hidden = state.mode !== 'custom';
  $('extrasInfo').hidden = state.mode !== 'custom';
  $('fileInfo').hidden = !(state.mode === 'custom' && state.src === 'file' && state.file);
  if (state.mode === 'quick') $('whatInfo').textContent = `Every graphics build: installs on any PC Tessera supports. A ${gb(f.size)} download.${have(f)}`;
  else if (state.mode === 'thispc') $('whatInfo').textContent = `Only the ${FLAVOR_NAMES[state.flavor]} build, for this PC (${state.gpu.cards.join(' + ')}). A ${gb(f.size)} download.${have(f)}`;
  else {
    $('whatInfo').textContent = 'Pick one:';
    const box = $('flavors');
    box.replaceChildren();
    const opts = [...['all', 'amd-intel', 'nvidia', 'nvidia-open'].map((k) => ({ k, x: fl[k] })), { k: 'file' }];
    for (const { k, x } of opts) {
      const lab = document.createElement('label');
      const off = k !== 'file' && !x;
      lab.className = 'choice' + (off ? ' off' : '');
      const inp = document.createElement('input');
      inp.type = 'radio'; inp.name = 'flavor'; inp.value = k; inp.disabled = off;
      inp.checked = k === 'file' ? state.src === 'file' : state.src === 'release' && state.flavor === k;
      const t = document.createElement('span');
      const mineTag = state.gpu && state.gpu.flavor === k ? ' · this PC' : '';
      t.textContent = k === 'file' ? 'An image file I already have' : FLAVOR_NAMES[k] + mineTag;
      const sz = document.createElement('span');
      sz.className = 'sz';
      sz.textContent = k === 'file' ? (state.file ? `${state.file.name} · ${gb(state.file.size)}` : 'choose…') : x ? `${gb(x.size)} · ${usbFor(x.size)} GB USB${x.downloaded ? ' · downloaded' : ''}` : 'not in this build yet';
      const left = document.createElement('span');
      left.style.display = 'flex'; left.style.gap = '8px'; left.style.alignItems = 'center';
      left.append(inp, t);
      lab.append(left, sz);
      inp.addEventListener('change', async () => {
        if (k === 'file') {
          const file = await window.mortar.chooseIso();
          if (!file) { paintWhat(); return; }
          state.file = file; state.src = 'file';
        } else { state.src = 'release'; state.flavor = k; }
        paintWhat(); renderDrives(); refresh();
      });
      box.append(lab);
    }
  }
  const need = needed();
  $('driveNeed').textContent = need ? `Plug in a USB drive of ${usbFor(need)} GB or more. Everything on it will be erased.` : 'Everything on it will be erased.';
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
  renderDrives();
  refresh();
}
function renderDrives() {
  const box = $('drives');
  box.replaceChildren();
  const need = needed();
  const fits = state.drives.filter((d) => !need || d.size >= need);
  if (!state.drive && fits.length === 1) state.drive = fits[0].id;
  if (state.drive && need && !fits.some((d) => d.id === state.drive)) state.drive = null;
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
    const small = Boolean(need) && d.size < need;
    b.disabled = small;
    b.innerHTML = driveIcon();
    const t = document.createElement('div');
    const nm = document.createElement('div'); nm.className = 'nm'; nm.textContent = d.name;
    const sub = document.createElement('div'); sub.className = 'sub';
    sub.textContent = [gb(d.size), d.bus, small ? 'too small for this' : d.mounts && d.mounts.length ? `in use at ${d.mounts[0]}` : ''].filter(Boolean).join(' · ');
    t.append(nm, sub);
    b.append(t);
    b.addEventListener('click', () => { state.drive = d.id; renderDrives(); refresh(); });
    box.append(b);
  }
}
function refresh() {
  const hasImage = state.src === 'file' ? Boolean(state.file) : Boolean(flavorsAvail()[state.flavor]);
  const d = state.drives.find((x) => x.id === state.drive);
  $('go').disabled = !(hasImage && d);
  $('goInfo').textContent = !hasImage ? 'Choose what goes on the USB first.' : !d ? 'Choose a USB drive.' : `Ready to write to ${d.name} (${gb(d.size)}).`;
}

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
  const r = await window.mortar.make({ driveId: d.id, source: state.src === 'file' ? { type: 'file', path: state.file.path } : { type: 'release', flavor: state.flavor } });
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
      + (state.src === 'release' && state.flavor !== 'all' ? `<li>This USB carries only the ${FLAVOR_NAMES[state.flavor]} build, so use it on PCs with that kind of graphics.</li>` : '')
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
$('again').addEventListener('click', () => { $('finished').hidden = true; $('choose').hidden = false; state.sig = ''; loadNewest(); loadDrives(); });
$('help').addEventListener('click', () => window.mortar.open('help'));
$('releasesLink').addEventListener('click', (e) => { e.preventDefault(); window.mortar.open('releases'); });
$('folderLink').addEventListener('click', (e) => { e.preventDefault(); window.mortar.open('folder'); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('confirm').hidden) $('confirmNo').click(); });

loadNewest();
loadGpu();
loadDrives();
setInterval(loadDrives, 2500);
