'use strict';
// Finds the newest Tessera USB image on GitHub Releases. Each image is published as a pre-release
// tagged usb-…, split into Tessera-Live.iso.partNN files (GitHub's 2 GB limit) plus a .sha256 file.
const { getText } = require('./http');

const REPO = process.env.MORTAR_REPO || 'Herbalchemist/tessera-mortar';
const API = process.env.MORTAR_API || 'https://api.github.com';

// Pure: turns the GitHub releases list into the images Mortar can use, newest first.
function pickImages(releases) {
  const out = [];
  for (const r of Array.isArray(releases) ? releases : []) {
    if (!r || typeof r.tag_name !== 'string' || !/^usb-/.test(r.tag_name) || r.draft) continue;
    const assets = Array.isArray(r.assets) ? r.assets : [];
    const parts = assets
      .filter((a) => /^Tessera-Live\.iso\.part\d+$/.test(a.name))
      .sort((a, b) => a.name.localeCompare(b.name, 'en', { numeric: true }))
      .map((a) => ({ name: a.name, url: a.browser_download_url, size: Number(a.size) || 0 }));
    const sum = assets.find((a) => a.name === 'Tessera-Live.iso.sha256');
    if (!parts.length || !sum) continue;
    // parts must be numbered 00, 01, … with no gaps
    if (parts.some((p, i) => Number(p.name.match(/part(\d+)$/)[1]) !== i)) continue;
    out.push({
      tag: r.tag_name,
      title: r.name || r.tag_name,
      published: r.published_at || r.created_at || '',
      prerelease: Boolean(r.prerelease),
      parts,
      size: parts.reduce((n, p) => n + p.size, 0),
      shaUrl: sum.browser_download_url,
      page: r.html_url || '',
    });
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
  const img = images[0];
  img.sha256 = parseSha(await getText(img.shaUrl));
  if (!img.sha256) throw new Error("The image's checksum file couldn't be read.");
  return img;
}

module.exports = { pickImages, parseSha, newest, REPO };
