'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { parseMigrationCheckOutput } = require('../main/pidfile');

test('parseMigrationCheckOutput parses an up_to_date payload', () => {
  const parsed = parseMigrationCheckOutput(
    '{"status": "up_to_date", "current": "e2f3a4b5c6d7", "heads": ["e2f3a4b5c6d7"], "up_to_date": true}\n'
  );
  assert.deepEqual(parsed, {
    status: 'up_to_date',
    current: 'e2f3a4b5c6d7',
    heads: ['e2f3a4b5c6d7'],
    upToDate: true,
    message: undefined,
  });
});

test('parseMigrationCheckOutput parses upgrade_required with no current revision', () => {
  const parsed = parseMigrationCheckOutput(
    '{"status": "upgrade_required", "current": null, "heads": ["abc"], "up_to_date": false}'
  );
  assert.equal(parsed.status, 'upgrade_required');
  assert.equal(parsed.current, null);
  assert.equal(parsed.upToDate, false);
  assert.deepEqual(parsed.heads, ['abc']);
});

test('parseMigrationCheckOutput tolerates log noise around the JSON line', () => {
  const noisy = 'INFO sqlalchemy\nsome startup line\n{"status": "error", "message": "boom"}\n';
  const parsed = parseMigrationCheckOutput(noisy);
  assert.equal(parsed.status, 'error');
  assert.equal(parsed.message, 'boom');
  assert.equal(parsed.upToDate, false);
});

test('parseMigrationCheckOutput returns null for garbage', () => {
  assert.equal(parseMigrationCheckOutput(''), null);
  assert.equal(parseMigrationCheckOutput('not json\n'), null);
  assert.equal(parseMigrationCheckOutput(null), null);
});
