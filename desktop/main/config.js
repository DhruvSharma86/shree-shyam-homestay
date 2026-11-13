'use strict';

/**
 * Desktop configuration handling.
 *
 * Secrets live OUTSIDE the installation directory, in
 *   %APPDATA%\ShreeShyamHomeStay\config.env
 * (a KEY=VALUE file). Resolution order:
 *   1. %APPDATA%\ShreeShyamHomeStay\config.env   (packaged app; production)
 *   2. development fallback: <repo>/backend/.env  (only when not packaged)
 *   3. nothing -> first-run setup screen
 *
 * Safety rails:
 *  - Configuration pointing at the disposable PostgreSQL recovery databases
 *    (sshs_drill_*) is rejected outright.
 *  - DATABASE_URL is required; everything else has a safe default.
 *  - SESSION_SECRET is never logged or sent to the renderer.
 */

const fs = require('fs');
const path = require('path');

const APP_DIR = 'ShreeShyamHomeStay';
const CONFIG_FILE = 'config.env';

const DISPOSABLE_DB_MARKERS = ['sshs_drill_source', 'sshs_drill_restore'];

/** Parse a KEY=VALUE dotenv-style text body. Never throws. */
function parseConfigEnv(text) {
  const out = {};
  if (typeof text !== 'string') return out;
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) out[key] = value;
  }
  return out;
}

/** Serialise a plain object back to config.env format (sorted, stable). */
function serializeConfigEnv(obj) {
  return Object.keys(obj)
    .sort()
    .map((k) => `${k}=${obj[k]}`)
    .join('\n') + '\n';
}

function isDisposableDatabaseUrl(url) {
  const u = String(url || '').toLowerCase();
  return DISPOSABLE_DB_MARKERS.some((m) => u.includes(m));
}

function normalisePort(value, fallback) {
  const n = Number.parseInt(String(value || ''), 10);
  return Number.isInteger(n) && n >= 1 && n <= 65535 ? n : fallback;
}

/**
 * Validate a raw config object. Returns { ok, errors[], config } where
 * `config` is the effective configuration with defaults applied.
 */
function resolveConfig(raw, options = {}) {
  const source = options.source || 'default';
  const errors = [];
  const cfg = { ...(raw || {}) };

  if (isDisposableDatabaseUrl(cfg.DATABASE_URL)) {
    errors.push(
      'DATABASE_URL points at a disposable recovery database (sshs_drill_*). ' +
        'The desktop application must use the "shree_shyam" database.'
    );
  }

  const databaseUrl = (cfg.DATABASE_URL || '').trim();
  if (!databaseUrl) {
    errors.push('DATABASE_URL is not set.');
  }

  const effective = {
    APP_ENV: (cfg.APP_ENV || 'production').trim().toLowerCase(),
    LOG_LEVEL: (cfg.LOG_LEVEL || 'INFO').trim().toUpperCase(),
    DATABASE_URL: databaseUrl,
    SESSION_SECRET: (cfg.SESSION_SECRET || '').trim(),
    CORS_ORIGINS: (cfg.CORS_ORIGINS || 'http://localhost:3000,http://127.0.0.1:3000').trim(),
    SESSION_IDLE_TIMEOUT_MINUTES: normalisePort(cfg.SESSION_IDLE_TIMEOUT_MINUTES, 30),
    SESSION_ABSOLUTE_TIMEOUT_HOURS: normalisePort(cfg.SESSION_ABSOLUTE_TIMEOUT_HOURS, 12),
    TRUSTED_PROXY_ENABLED: 'false',
  };

  return { ok: errors.length === 0, errors, config: effective, source };
}

/** Resolve the effective configuration from disk. Never throws. */
function loadConfig({ appDataDir, repoBackendEnv, isPackaged }) {
  const appDataConfig = path.join(appDataDir, CONFIG_FILE);
  try {
    if (fs.existsSync(appDataConfig)) {
      const raw = parseConfigEnv(fs.readFileSync(appDataConfig, 'utf8'));
      return { ...resolveConfig(raw, { source: 'appdata' }), path: appDataConfig };
    }
  } catch {
    // fall through — unreadable file is reported by the caller flow
  }
  if (!isPackaged && repoBackendEnv && fs.existsSync(repoBackendEnv)) {
    try {
      const raw = parseConfigEnv(fs.readFileSync(repoBackendEnv, 'utf8'));
      return { ...resolveConfig(raw, { source: 'development' }), path: repoBackendEnv };
    } catch {
      /* fall through */
    }
  }
  return { ...resolveConfig({}, { source: 'missing' }), path: appDataConfig };
}

/** Environment passed to the backend child process (contains secrets — never log). */
function backendChildEnv(effective) {
  return {
    ...process.env,
    DATABASE_URL: effective.DATABASE_URL,
    APP_ENV: effective.APP_ENV,
    LOG_LEVEL: effective.LOG_LEVEL,
    SESSION_SECRET: effective.SESSION_SECRET,
    SESSION_IDLE_TIMEOUT_MINUTES: String(effective.SESSION_IDLE_TIMEOUT_MINUTES),
    SESSION_ABSOLUTE_TIMEOUT_HOURS: String(effective.SESSION_ABSOLUTE_TIMEOUT_HOURS),
    TRUSTED_PROXY_ENABLED: effective.TRUSTED_PROXY_ENABLED,
    CORS_ORIGINS: effective.CORS_ORIGINS,
    DESKTOP_BACKEND_PORT: '8000',
    // Never inherit a stray DATABASE_URL override from a parent shell silently;
    // process.env spread above is intentional for PATH/SystemRoot etc., but the
    // desktop-managed values above always win.
  };
}

module.exports = {
  APP_DIR,
  CONFIG_FILE,
  DISPOSABLE_DB_MARKERS,
  parseConfigEnv,
  serializeConfigEnv,
  isDisposableDatabaseUrl,
  resolveConfig,
  loadConfig,
  backendChildEnv,
};
