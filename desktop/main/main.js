'use strict';

/**
 * Shree Shyam Home Stay — desktop main process.
 *
 * Responsibilities:
 *  - Single application instance (second launch focuses the existing window).
 *  - Secure configuration resolution (see ./config.js — secrets never ship
 *    in the installation directory and never reach the renderer).
 *  - Safe, read-only checks before starting anything:
 *      a. PostgreSQL must be reachable AND the schema up to date
 *         (`ShreeShyamBackend.exe --check-migration`, no mutations).
 *      b. Ports 8000 / 3000 must be free — or provably ours (stale orphan).
 *         Anything else occupying them is left untouched.
 *  - Lifecycle for the packaged FastAPI backend and the packaged Next.js
 *    standalone server (spawn / readiness probe / clean shutdown).
 *  - Native window with startup progress, first-run setup and error screens.
 *
 * The renderer never gets Node integration, filesystem access, process
 * control or secrets; it only displays pages served by the bundled app.
 */

const { app, BrowserWindow, ipcMain, Menu, shell } = require('electron');
const { spawn, execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const net = require('net');
const crypto = require('crypto');

const {
  APP_DIR,
  loadConfig,
  resolveConfig,
  serializeConfigEnv,
  backendChildEnv,
} = require('./config');
const { isPortFree, httpGetJson, pollUntil } = require('./ports');
const {
  pidFilePath,
  readPidFile,
  writePidFile,
  removePidFile,
  parseMigrationCheckOutput,
} = require('./pidfile');

const APP_TITLE = 'Shree Shyam Home Stay';
const APP_ORIGIN = 'http://localhost:3000';
const BACKEND_BASE = 'http://127.0.0.1:8000';
const APP_ORIGIN_ALTS = new Set(['http://localhost:3000', 'http://127.0.0.1:3000']);
const EXPECTED_BACKEND_NAME = 'Shree Shyam Home Stay';

const isPackaged = app.isPackaged;
const appRoot = path.resolve(__dirname, '..'); // desktop/
const repoRoot = path.resolve(appRoot, '..');

const appDataDir = path.join(
  process.env.APPDATA || path.join(require('os').homedir(), 'AppData', 'Roaming'),
  APP_DIR
);
const logsDir = path.join(appDataDir, 'logs');

const paths = {
  backendExe: isPackaged
    ? path.join(process.resourcesPath, 'backend', 'ShreeShyamBackend.exe')
    : path.join(repoRoot, 'backend', 'packaging', 'dist', 'ShreeShyamBackend', 'ShreeShyamBackend.exe'),
  frontendServer: isPackaged
    ? path.join(process.resourcesPath, 'frontend', 'standalone', 'server.js')
    : path.join(repoRoot, 'frontend', '.next', 'standalone', 'server.js'),
  nodeExe: isPackaged
    ? path.join(process.resourcesPath, 'node', 'node.exe')
    : process.env.SHREE_SHYAM_NODE || 'node',
  backendPid: pidFilePath(appDataDir, 'backend'),
  frontendPid: pidFilePath(appDataDir, 'frontend'),
};

/** @type {import('child_process').ChildProcess | null} */
let backendChild = null;
/** @type {import('child_process').ChildProcess | null} */
let frontendChild = null;
/** @type {BrowserWindow | null} */
let mainWindow = null;
let quitting = false;
let effectiveConfig = null;

function ensureDirs() {
  fs.mkdirSync(logsDir, { recursive: true });
}

function rotateLog(name) {
  try {
    const file = path.join(logsDir, name);
    if (fs.existsSync(file) && fs.statSync(file).size > 1024 * 1024) {
      fs.renameSync(file, path.join(logsDir, `${name}.1`));
    }
  } catch {
    /* best effort */
  }
}

/** Append a line to the desktop log. Never pass secrets in `msg`. */
function log(level, msg) {
  try {
    ensureDirs();
    const line = `[${new Date().toISOString()}] [${level}] ${msg}\n`;
    fs.appendFileSync(path.join(logsDir, 'desktop.log'), line);
    console.log(line.trimEnd());
  } catch {
    /* logging must never crash the app */
  }
}

/** Child stdout/stderr goes to its own log file; secrets are never emitted. */
function pipeChildOutput(child, name) {
  try {
    rotateLog(name);
    const stream = fs.createWriteStream(path.join(logsDir, name), { flags: 'a' });
    if (child.stdout) child.stdout.pipe(stream);
    if (child.stderr) child.stderr.pipe(stream);
  } catch (err) {
    log('warn', `Could not attach log file ${name}: ${err.message}`);
  }
}

function readLogTail(name, maxBytes = 8192) {
  try {
    const file = path.join(logsDir, name);
    if (!fs.existsSync(file)) return '';
    const { size } = fs.statSync(file);
    const start = Math.max(0, size - maxBytes);
    const fd = fs.openSync(file, 'r');
    const buf = Buffer.alloc(size - start);
    fs.readSync(fd, buf, 0, buf.length, start);
    fs.closeSync(fd);
    return buf.toString('utf8');
  } catch {
    return '';
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    title: APP_TITLE,
    show: false,
    backgroundColor: '#14532d',
    autoHideMenuBar: true,
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
      devTools: process.env.SHREE_SHYAM_DESKTOP_DEV === '1',
    },
  });
  Menu.setApplicationMenu(null);

  mainWindow.once('ready-to-show', () => mainWindow?.show());
  mainWindow.on('closed', () => {
    mainWindow = null;
    quitApp();
  });

  // Navigation is locked to the bundled app origin.
  mainWindow.webContents.on('will-navigate', (event, url) => {
    try {
      const { origin } = new URL(url);
      if (!APP_ORIGIN_ALTS.has(origin)) event.preventDefault();
    } catch {
      event.preventDefault();
    }
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-attach-webview', (event) => event.preventDefault());

  mainWindow.loadFile(path.join(__dirname, 'loading.html'));
}

function sendStatus(message) {
  try {
    mainWindow?.webContents.send('desktop:status', String(message));
  } catch {
    /* window may be gone */
  }
}

function showError(title, detail) {
  log('error', `${title}: ${detail}`);
  sendStatus('Error');
  if (!mainWindow) createWindow();
  if (!mainWindow) return;
  const hash = encodeURIComponent(JSON.stringify({ title, detail }));
  mainWindow.loadFile(path.join(__dirname, 'error.html'), { hash });
}

function showSetup() {
  log('info', 'No configuration found — showing first-run setup.');
  if (!mainWindow) createWindow();
  mainWindow?.loadFile(path.join(__dirname, 'setup.html'));
}

/** Kill a specific pid tree (Windows) — used ONLY for processes we provably own. */
function killPidTree(pid) {
  return new Promise((resolve) => {
    if (!Number.isInteger(pid) || pid <= 0) return resolve(false);
    execFile(
      'taskkill',
      ['/PID', String(pid), '/T', '/F'],
      { windowsHide: true, timeout: 15000 },
      (err) => resolve(!err)
    );
  });
}

function imageNameOf(pid) {
  return new Promise((resolve) => {
    execFile(
      'tasklist',
      ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'],
      { windowsHide: true, timeout: 10000 },
      (err, stdout) => {
        if (err || !stdout) return resolve(null);
        const first = stdout.trim().split(/\r?\n/)[0] || '';
        const match = first.match(/^"([^"]+)"/);
        resolve(match ? match[1].toLowerCase() : null);
      }
    );
  });
}

/** Terminate a stale child we own (pid file + image match). Leaves others alone. */
async function reapStaleChild(name, expectedImage) {
  const pidFile = name === 'backend' ? paths.backendPid : paths.frontendPid;
  const pid = readPidFile(pidFile);
  if (!pid) return false;
  const image = await imageNameOf(pid);
  if (image === expectedImage) {
    log('warn', `Reaping stale ${name} process (pid ${pid}).`);
    const ok = await killPidTree(pid);
    removePidFile(pidFile);
    return ok;
  }
  removePidFile(pidFile);
  return false;
}

function runBackendMigrationCheck() {
  return new Promise((resolve) => {
    const child = spawn(paths.backendExe, ['--check-migration'], {
      windowsHide: true,
      cwd: logsDir,
      env: { ...process.env, ...configEnvOnly() },
    });
    // Hard cap: an unresponsive database must never hang the startup flow.
    const KILLED = { status: 'error', upToDate: false, heads: [], current: null };
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => {
      log('error', 'Migration status check timed out — terminating the check process.');
      if (child.pid) killPidTree(child.pid).then(() => {});
      finish(KILLED);
    }, 25000);
    let out = '';
    child.stdout?.on('data', (d) => {
      if (out.length < 65536) out += d.toString('utf8');
    });
    child.stderr?.on('data', () => {}); // never surface engine errors with URLs
    child.on('error', () => finish(KILLED));
    child.on('close', (code) => {
      const parsed = parseMigrationCheckOutput(out);
      if (parsed) return finish(parsed);
      finish({ ...KILLED, code });
    });
  });
}

function configEnvOnly() {
  if (!effectiveConfig) return {};
  return {
    DATABASE_URL: effectiveConfig.DATABASE_URL,
    APP_ENV: effectiveConfig.APP_ENV,
    LOG_LEVEL: effectiveConfig.LOG_LEVEL,
    SESSION_SECRET: effectiveConfig.SESSION_SECRET,
    SESSION_IDLE_TIMEOUT_MINUTES: String(effectiveConfig.SESSION_IDLE_TIMEOUT_MINUTES),
    SESSION_ABSOLUTE_TIMEOUT_HOURS: String(effectiveConfig.SESSION_ABSOLUTE_TIMEOUT_HOURS),
    TRUSTED_PROXY_ENABLED: 'false',
    CORS_ORIGINS: effectiveConfig.CORS_ORIGINS,
  };
}

async function backendReady() {
  return pollUntil(
    async () => {
      const res = await httpGetJson(`${BACKEND_BASE}/health/ready`, 2000);
      return res && res.status === 200 ? res : null;
    },
    { timeoutMs: 90000, intervalMs: 1000 }
  );
}

async function frontendReady() {
  return pollUntil(
    async () => {
      const res = await httpGetJson(`${APP_ORIGIN}/login`, 3000);
      return res && res.status >= 200 && res.status < 400 ? res : null;
    },
    { timeoutMs: 60000, intervalMs: 1000 }
  );
}

/** Identify a service already listening on our backend port. */
async function identifyBackendOnPort() {
  const res = await httpGetJson(`${BACKEND_BASE}/health`, 2500);
  if (res && res.body && typeof res.body.app === 'string' && res.body.app.includes(EXPECTED_BACKEND_NAME)) {
    return 'ours';
  }
  return res ? 'unknown' : 'unknown';
}

async function startBackend() {
  sendStatus('Starting database services…');
  const free = await isPortFree(8000, '127.0.0.1');
  if (!free) {
    const who = await identifyBackendOnPort();
    const reaped = who === 'ours' && (await reapStaleChild('backend', 'shreeshyambackend.exe'));
    if (!reaped || !(await isPortFree(8000, '127.0.0.1'))) {
      showError(
        'Port 8000 is in use',
        'Another application is already listening on port 8000. ' +
          'Close it or ask your administrator to free the port, then start Shree Shyam Home Stay again. ' +
          'The application was not terminated and no changes were made.'
      );
      return false;
    }
  }

  if (!fs.existsSync(paths.backendExe)) {
    showError('Backend not found', 'The packaged backend executable is missing. Please reinstall the application.');
    return false;
  }

  backendChild = spawn(paths.backendExe, [], {
    windowsHide: true,
    cwd: logsDir,
    env: backendChildEnv(effectiveConfig),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  writePidFile(paths.backendPid, backendChild.pid);
  pipeChildOutput(backendChild, 'backend.log');

  backendChild.on('exit', (code) => {
    removePidFile(paths.backendPid);
    if (!quitting) {
      log('error', `Backend exited unexpectedly (code ${code}).`);
      showError(
        'The backend stopped unexpectedly',
        `The database service exited with code ${code}. Recent log output is shown below.\n\n${readLogTail('backend.log', 4000)}`
      );
      stopFrontend();
    }
  });

  const ready = await backendReady();
  if (!ready) {
    showError(
      'Cannot connect to PostgreSQL',
      'The application could not reach the database. Check that:\n\n' +
        '  1. PostgreSQL is running (Windows service “postgresql-x64-18”),\n' +
        '  2. DATABASE_URL in %APPDATA%\\ShreeShyamHomeStay\\config.env is correct,\n' +
        '  3. the “shree_shyam” database exists and the user has access.\n\n' +
        `Recent log output:\n\n${readLogTail('backend.log', 4000)}`
    );
    stopFrontend();
    stopBackend(); // the backend may be alive but unreachable — never orphan it
    return false;
  }
  log('info', 'Backend ready (database connectivity verified).');
  return true;
}

async function startFrontend() {
  sendStatus('Starting the application interface…');
  const free = await isPortFree(3000, '127.0.0.1');
  if (!free) {
    const res = await httpGetJson(`${APP_ORIGIN}/login`, 2500);
    const looksOurs = res && res.status >= 200 && res.status < 400;
    const reaped = looksOurs && (await reapStaleChild('frontend', 'node.exe'));
    if (!reaped || !(await isPortFree(3000, '127.0.0.1'))) {
      showError(
        'Port 3000 is in use',
        'Another application is already listening on port 3000. ' +
          'Close it or ask your administrator to free the port, then start Shree Shyam Home Stay again. ' +
          'The application was not terminated and no changes were made.'
      );
      return false;
    }
  }

  if (!fs.existsSync(paths.frontendServer)) {
    showError('Frontend not found', 'The packaged web application is missing. Please reinstall the application.');
    return false;
  }
  if (isPackaged && !fs.existsSync(paths.nodeExe)) {
    showError('Node.js runtime not found', 'The bundled Node.js runtime is missing. Please reinstall the application.');
    return false;
  }

  frontendChild = spawn(
    paths.nodeExe,
    [paths.frontendServer],
    {
      windowsHide: true,
      cwd: path.dirname(paths.frontendServer),
      env: { ...process.env, NODE_ENV: 'production', PORT: '3000', HOSTNAME: '127.0.0.1' },
      stdio: ['ignore', 'pipe', 'pipe'],
    }
  );
  writePidFile(paths.frontendPid, frontendChild.pid);
  pipeChildOutput(frontendChild, 'frontend.log');

  frontendChild.on('exit', (code) => {
    removePidFile(paths.frontendPid);
    if (!quitting) {
      log('error', `Frontend exited unexpectedly (code ${code}).`);
      showError(
        'The interface stopped unexpectedly',
        `The interface service exited with code ${code}. Recent log output is shown below.\n\n${readLogTail('frontend.log', 4000)}`
      );
      stopBackend();
    }
  });

  const ready = await frontendReady();
  if (!ready) {
    showError(
      'The interface did not start',
      `Recent log output:\n\n${readLogTail('frontend.log', 4000)}`
    );
    return false;
  }
  log('info', 'Frontend ready.');
  return true;
}

function stopBackend() {
  if (backendChild) {
    const child = backendChild;
    backendChild = null;
    if (child.pid) killPidTree(child.pid).then(() => {});
  }
  removePidFile(paths.backendPid);
}

function stopFrontend() {
  if (frontendChild) {
    const child = frontendChild;
    frontendChild = null;
    if (child.pid) killPidTree(child.pid).then(() => {});
  }
  removePidFile(paths.frontendPid);
}

function stopChildren() {
  stopFrontend();
  stopBackend();
}

function quitApp() {
  if (quitting) return;
  quitting = true;
  stopChildren();
  app.quit();
}

async function startup() {
  try {
    ensureDirs();
    rotateLog('desktop.log');

    sendStatus('Checking configuration…');
    const loaded = loadConfig({
      appDataDir,
      repoBackendEnv: path.join(repoRoot, 'backend', '.env'),
      isPackaged,
    });

    if (loaded.source === 'missing' || !loaded.ok) {
      if (loaded.source === 'missing') {
        showSetup();
        return;
      }
      showError(
        'Configuration problem',
        (loaded.errors || ['The configuration file could not be read.']).join('\n') +
          `\n\nFile: ${loaded.path}`
      );
      return;
    }
    effectiveConfig = loaded.config;
    if (loaded.source === 'development') {
      log('warn', 'Using backend/.env development configuration (unpackaged build).');
    }

    // Guarantee a persistent SESSION_SECRET — generate once and persist it,
    // so sessions survive restarts without ever shipping a default secret.
    if (!effectiveConfig.SESSION_SECRET) {
      const generated = crypto.randomBytes(48).toString('base64url');
      const file = path.join(appDataDir, 'config.env');
      try {
        const existing = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
        fs.writeFileSync(file, existing + `SESSION_SECRET=${generated}\n`, { mode: 0o600 });
        effectiveConfig = { ...effectiveConfig, SESSION_SECRET: generated };
        log('info', 'Generated and persisted a new SESSION_SECRET in config.env.');
      } catch (err) {
        showError('Configuration problem', `SESSION_SECRET is missing and could not be generated: ${err.message}`);
        return;
      }
    }

    sendStatus('Checking database schema…');
    if (!fs.existsSync(paths.backendExe)) {
      showError('Backend not found', 'The packaged backend executable is missing. Please reinstall the application.');
      return;
    }
    const check = await runBackendMigrationCheck();
    if (!check.upToDate) {
      if (check.status === 'upgrade_required') {
        showError(
          'Database upgrade required',
          `The “shree_shyam” database is not at the expected migration (current: ${check.current || 'none'}; expected: ${(check.heads || []).join(', ')}).\n\n` +
            'The application will NOT run migrations automatically. To upgrade safely:\n\n' +
            '  1. Back up the database first (see docs/OPERATIONS.md — ops/backup-postgres.ps1).\n' +
            '  2. From a source checkout: cd backend && alembic upgrade head\n' +
            '  3. Start Shree Shyam Home Stay again.\n\n' +
            'No data was changed.'
        );
      } else {
        showError(
          'Cannot connect to PostgreSQL',
          'The database could not be verified. Check that PostgreSQL is running and that DATABASE_URL in %APPDATA%\\ShreeShyamHomeStay\\config.env is correct.\n\nNo data was changed.'
        );
      }
      return;
    }

    if (!(await startBackend())) return;
    sendStatus('Almost ready…');
    if (!(await startFrontend())) {
      stopBackend();
      return;
    }

    sendStatus('Opening your workspace…');
    mainWindow?.loadURL(`${APP_ORIGIN}/`);
    log('info', 'Desktop application started.');
  } catch (err) {
    log('error', `Startup failure: ${err && err.stack ? err.stack : err}`);
    showError('Startup failed', 'An unexpected error occurred while starting the application. See %APPDATA%\\ShreeShyamHomeStay\\logs\\desktop.log for details.');
    stopChildren();
  }
}

// ---------------------------------------------------------------------------
// Single instance — a second launch focuses the running window.
// ---------------------------------------------------------------------------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.on('ready', () => {
    ensureDirs();
    createWindow();
    startup();
  });

  app.on('before-quit', () => {
    quitting = true;
    stopChildren();
  });

  app.on('window-all-closed', () => {
    quitApp();
  });

  // ------------------------------------------------------------------ IPC:
  // The renderer may only (a) receive status strings, (b) submit the
  // first-run form. Nothing else is exposed (see preload.js).
  // ------------------------------------------------------------------
  ipcMain.handle('desktop:setup-submit', async (_event, fields) => {
    try {
      const f = fields && typeof fields === 'object' ? fields : {};
      const host = String(f.host || 'localhost').trim();
      const port = Number.parseInt(String(f.port || '5432'), 10);
      const database = String(f.database || 'shree_shyam').trim();
      const username = String(f.username || '').trim();
      const password = String(f.password || '');

      if (!/^[A-Za-z0-9.\-]+$/.test(host)) return { ok: false, error: 'Host contains invalid characters.' };
      if (!/^[A-Za-z0-9_\-]+$/.test(database)) return { ok: false, error: 'Database name contains invalid characters.' };
      if (!username) return { ok: false, error: 'Username is required.' };
      if (!password) return { ok: false, error: 'Password is required.' };
      if (!Number.isInteger(port) || port < 1 || port > 65535) return { ok: false, error: 'Port must be 1–65535.' };

      const reachable = await new Promise((resolve) => {
        const socket = new net.Socket();
        socket.setTimeout(3000);
        socket.once('connect', () => { socket.destroy(); resolve(true); });
        socket.once('timeout', () => { socket.destroy(); resolve(false); });
        socket.once('error', () => { socket.destroy(); resolve(false); });
        socket.connect(port, host);
      });
      if (!reachable) {
        return { ok: false, error: `PostgreSQL is not reachable at ${host}:${port}. Check that the service is running.` };
      }

      const url = `postgresql+psycopg://${encodeURIComponent(username)}:${encodeURIComponent(password)}@${host}:${port}/${encodeURIComponent(database)}`;
      const secret = crypto.randomBytes(48).toString('base64url');
      const file = path.join(appDataDir, 'config.env');
      const content =
        `# Shree Shyam Home Stay — local configuration (per-user, outside the install directory)\n` +
        `APP_ENV=production\n` +
        `LOG_LEVEL=INFO\n` +
        `DATABASE_URL=${url}\n` +
        `SESSION_SECRET=${secret}\n` +
        `CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000\n`;
      ensureDirs();
      fs.writeFileSync(file, content, { mode: 0o600 });
      log('info', 'First-run configuration written (secrets not logged).');
      startup(); // continue with the new configuration
      return { ok: true };
    } catch (err) {
      log('error', `Setup failed: ${err && err.message ? err.message : err}`);
      return { ok: false, error: 'Could not save the configuration. Check the logs folder for details.' };
    }
  });

  // Guard against crashes taking down the machine state: best effort cleanup.
  process.on('uncaughtException', (err) => {
    log('error', `uncaughtException: ${err && err.stack ? err.stack : err}`);
    stopChildren();
    app.exit(1);
  });
}
