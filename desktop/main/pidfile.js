'use strict';

/**
 * PID-file management for child processes.
 *
 * Purpose: on Windows a hard main-process crash can orphan the backend /
 * frontend child processes, which then hold ports 8000/3000. On next launch we
 * only ever terminate a process when it is BOTH (a) listed in our own pid
 * file AND (b) recognised as our backend/frontend image. Anything else is
 * left strictly alone.
 */

const fs = require('fs');
const path = require('path');

function pidFilePath(dir, name) {
  return path.join(dir, `${name}.pid`);
}

/** Read and validate a pid file. Returns pid (number) or null. Never throws. */
function readPidFile(filePath) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8').trim();
    const pid = Number.parseInt(raw, 10);
    if (!Number.isInteger(pid) || pid <= 0) return null;
    return pid;
  } catch {
    return null;
  }
}

function writePidFile(filePath, pid) {
  try {
    fs.writeFileSync(filePath, String(pid), 'utf8');
    return true;
  } catch {
    return false;
  }
}

function removePidFile(filePath) {
  try {
    fs.unlinkSync(filePath);
  } catch {
    /* already gone */
  }
}

/** PID (number) from a check-migration JSON payload, if present — helper kept
 * here to keep process-spawn parsing in one place. */
function parseMigrationCheckOutput(text) {
  if (typeof text !== 'string') return null;
  const line = text
    .trim()
    .split(/\r?\n/)
    .map((l) => l.trim())
    .reverse()
    .find((l) => l.startsWith('{'));
  if (!line) return null;
  try {
    const parsed = JSON.parse(line);
    return {
      status: String(parsed.status || 'error'),
      current: parsed.current ?? null,
      heads: Array.isArray(parsed.heads) ? parsed.heads.map(String) : [],
      upToDate: parsed.up_to_date === true,
      message: typeof parsed.message === 'string' ? parsed.message : undefined,
    };
  } catch {
    return null;
  }
}

module.exports = {
  pidFilePath,
  readPidFile,
  writePidFile,
  removePidFile,
  parseMigrationCheckOutput,
};
