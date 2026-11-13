'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  parseConfigEnv,
  serializeConfigEnv,
  resolveConfig,
  isDisposableDatabaseUrl,
  DISPOSABLE_DB_MARKERS,
} = require('../main/config');

test('parseConfigEnv parses KEY=VALUE with comments and quotes', () => {
  const parsed = parseConfigEnv(
    [
      '# comment',
      'DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/shree_shyam',
      'SESSION_SECRET="quoted-secret"',
      "SINGLE='quoted'",
      '',
      'INVALID LINE',
      'APP_ENV=production',
    ].join('\n')
  );
  assert.equal(parsed.DATABASE_URL, 'postgresql+psycopg://u:p@localhost:5432/shree_shyam');
  assert.equal(parsed.SESSION_SECRET, 'quoted-secret');
  assert.equal(parsed.SINGLE, 'quoted');
  assert.equal(parsed.APP_ENV, 'production');
  assert.equal(Object.keys(parsed).length, 4);
});

test('serializeConfigEnv round-trips through parseConfigEnv', () => {
  const obj = { DATABASE_URL: 'postgresql+psycopg://u:p@h/db', SESSION_SECRET: 'abc123', APP_ENV: 'production' };
  const roundTripped = parseConfigEnv(serializeConfigEnv(obj));
  assert.deepEqual(roundTripped, obj);
});

test('resolveConfig requires DATABASE_URL', () => {
  const { ok, errors, config } = resolveConfig({});
  assert.equal(ok, false);
  assert.ok(errors.some((e) => e.includes('DATABASE_URL')));
  assert.equal(config.APP_ENV, 'production'); // default applied anyway
});

test('resolveConfig applies safe defaults', () => {
  const { ok, config } = resolveConfig({ DATABASE_URL: 'postgresql+psycopg://u:p@localhost/shree_shyam' });
  assert.equal(ok, true);
  assert.equal(config.SESSION_IDLE_TIMEOUT_MINUTES, 30);
  assert.equal(config.SESSION_ABSOLUTE_TIMEOUT_HOURS, 12);
  assert.equal(config.TRUSTED_PROXY_ENABLED, 'false');
  assert.ok(config.CORS_ORIGINS.includes('http://localhost:3000'));
});

test('resolveConfig rejects disposable recovery databases', () => {
  for (const marker of DISPOSABLE_DB_MARKERS) {
    const { ok, errors } = resolveConfig({ DATABASE_URL: `postgresql+psycopg://u:p@localhost/${marker}_2026` });
    assert.equal(ok, false, `marker ${marker} must be rejected`);
    assert.ok(errors[0].includes('disposable'));
  }
});

test('isDisposableDatabaseUrl is case-insensitive', () => {
  assert.equal(isDisposableDatabaseUrl('postgresql+psycopg://u:p@H/SSHS_DRILL_SOURCE_20261113'), true);
  assert.equal(isDisposableDatabaseUrl('postgresql+psycopg://u:p@localhost/shree_shyam'), false);
});

test('resolveConfig rejects garbage ports with fallback', () => {
  const { config } = resolveConfig({
    DATABASE_URL: 'postgresql+psycopg://u:p@localhost/shree_shyam',
    SESSION_IDLE_TIMEOUT_MINUTES: 'not-a-number',
  });
  assert.equal(config.SESSION_IDLE_TIMEOUT_MINUTES, 30);
});
