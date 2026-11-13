'use strict';

/** TCP/HTTP readiness probes used by the main process. */

const net = require('net');
const http = require('http');

/** Resolve true when nothing is accepting TCP connections on host:port. */
function isPortFree(port, host = '127.0.0.1', timeoutMs = 1500) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const done = (free) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(free);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => done(false));
    socket.once('timeout', () => done(true));
    socket.once('error', () => done(true));
    socket.connect(port, host);
  });
}

/** GET JSON with timeout; never throws. Returns { status, body? } or null. */
function httpGetJson(url, timeoutMs = 2000) {
  return new Promise((resolve) => {
    const req = http.get(
      url,
      { timeout: timeoutMs, headers: { Accept: 'application/json' } },
      (res) => {
        let data = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => {
          data += chunk;
          if (data.length > 65536) req.destroy();
        });
        res.on('end', () => {
          let body = null;
          try {
            body = JSON.parse(data);
          } catch {
            body = null;
          }
          resolve({ status: res.statusCode || 0, body });
        });
      }
    );
    req.on('timeout', () => {
      req.destroy();
      resolve(null);
    });
    req.on('error', () => resolve(null));
  });
}

/** Poll `probe` until it returns truthy or the deadline passes. */
async function pollUntil(probe, { timeoutMs = 60000, intervalMs = 1000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = await probe();
    if (value) return value;
    if (Date.now() > deadline) return null;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

module.exports = { isPortFree, httpGetJson, pollUntil };
