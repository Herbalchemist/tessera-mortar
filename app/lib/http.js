'use strict';
// Minimal HTTPS (or HTTP, for tests) client: follows redirects, supports Range requests and
// cancelling. Uses only Node's built-ins, so Mortar has no runtime dependencies.
const https = require('https');
const http = require('http');

const UA = 'tessera-mortar';

function request(url, { headers = {}, signal, redirects = 6 } = {}) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('http://') ? http : https;
    const req = lib.get(url, { headers: { 'User-Agent': UA, Accept: '*/*', ...headers } }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) {
        res.resume();
        if (redirects <= 0) return reject(new Error('Too many redirects.'));
        return resolve(request(new URL(res.headers.location, url).toString(), { headers, signal, redirects: redirects - 1 }));
      }
      resolve(res);
    });
    req.on('error', reject);
    req.setTimeout(60000, () => req.destroy(new Error('The download timed out.')));
    if (signal) {
      if (signal.aborted) req.destroy(new Error('Cancelled.'));
      signal.addEventListener('abort', () => req.destroy(new Error('Cancelled.')), { once: true });
    }
  });
}

async function getText(url, opts = {}) {
  const res = await request(url, { headers: { Accept: 'application/vnd.github+json, text/plain, */*' }, ...opts });
  const chunks = [];
  for await (const c of res) chunks.push(c);
  const body = Buffer.concat(chunks).toString('utf8');
  if (res.statusCode !== 200) {
    if (res.statusCode === 403 && /rate limit/i.test(body)) throw new Error("GitHub's limit for checking releases was reached. Wait a few minutes and try again.");
    throw new Error(`Couldn't reach GitHub (${res.statusCode}).`);
  }
  return body;
}

module.exports = { request, getText };
