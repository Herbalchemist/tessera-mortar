'use strict';
// Finds the newest Tessera USB images on GitHub Releases. Each build is published as a pre-release
// tagged usb-…, holding up to four ISOs ("flavors"), each split into .partNN files (GitHub's 2 GB
// limit) with a .sha256:
//   Tessera-Live.iso                 every graphics build (installs on any PC)   flavor "all"
//   Tessera-Live-amd-intel.iso       AMD / Intel only                            flavor "amd-intel"
//   Tessera-Live-nvidia.iso          NVIDIA GTX 900-1000 only                    flavor "nvidia"
//   Tessera-Live-nvidia-open.iso     NVIDIA GTX 16 / RTX only                    flavor "nvidia-open"
//   Tessera-Live-online.iso          the installer only; downloads the build      flavor "online"
//                                    while installing (needs internet then)
const { getText } = require('./http');

const REPO = process.env.MORTAR_REPO || 'Herbalchemist/tessera-mortar';
const API = process.env.MORTAR_API || 'https://api.github.com';
const FLAVORS = ['all', 'amd-intel', 'nvidia', 'nvidia-open', 'online'];
const isoName = (flavor) => (flavor === 'all' ? 'Tessera-Live.iso' : `Tessera-Live-${flavor}.iso`);

function flavorOf(assets, flavor) {
  const base = isoName(flavor);
  const rx = new RegExp(`^${base.replace(/\./g, '\\.')}\\.part(\\d+)$`);
  const parts = assets
    .filter((a) => rx.test(a.name))
    .map((a) => ({ name: a.name, url: a.browser_download_url, size: Number(a.size) || 0, n: Number(a.name.match(rx)[1]) }))
    .sort((a, b) => a.n - b.n);
  const sum = assets.find((a) => a.name === `${base}.sha256`);
  if (!parts.length || !sum || parts.some((p, i) => p.n !== i)) return null;
  return { file: base, parts: parts.map(({ n, ...p }) => p), size: parts.reduce((t, p) => t + p.size, 0), shaUrl: sum.browser_download_url };
}

// Pure: turns the GitHub releases list into usable builds, newest first.
function pickImages(releases) {
  const out = [];
  for (const r of Array.isArray(releases) ? releases : []) {
    if (!r || typeof r.tag_name !== 'string' || !/^usb-/.test(r.tag_name) || r.draft) continue;
    const assets = Array.isArray(r.assets) ? r.assets : [];
    const flavors = {};
    for (const f of FLAVORS) { const x = flavorOf(assets, f); if (x) flavors[f] = x; }
    if (!Object.keys(flavors).length) continue;
    out.push({ tag: r.tag_name, title: r.name || r.tag_name, published: r.published_at || r.created_at || '', page: r.html_url || '', flavors });
  }
  out.sort((a, b) => String(b.published).localeCompare(String(a.published)));
  return out;
}

// "abc123…  Tessera-Live.iso" -> "abc123…"
function parseSha(text) {
  const m = /^([0-9a-f]{64})\b/im.exec(String(text || ''));
  return m ? m[1].toLowerCase() : null;
}

async function newest() {
  const list = JSON.parse(await getText(`${API}/repos/${REPO}/releases?per_page=30`));
  const images = pickImages(list);
  if (!images.length) throw new Error('No Tessera USB image has been published yet.');
  return images[0];
}

async function shaOf(flavorInfo) {
  const sha = parseSha(await getText(flavorInfo.shaUrl));
  if (!sha) throw new Error("The image's checksum file couldn't be read.");
  return sha;
}

module.exports = { pickImages, parseSha, newest, shaOf, isoName, FLAVORS, REPO };
