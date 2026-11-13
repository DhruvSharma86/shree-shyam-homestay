// Assemble the staged Next.js standalone server for the desktop installer.
// Usage: node scripts/prepare-frontend.mjs
import { cpSync, existsSync, rmSync, statSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const desktopDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = join(desktopDir, '..');
const frontendDir = join(repoRoot, 'frontend');
const standalone = join(frontendDir, '.next', 'standalone');
const staging = join(desktopDir, '.cache', 'staging', 'frontend', 'standalone');

function die(message) {
  console.error(`prepare-frontend: ${message}`);
  process.exit(1);
}

if (!existsSync(join(standalone, 'server.js'))) {
  die(`${standalone} not found — run "npm run build" in frontend/ first.`);
}

rmSync(staging, { recursive: true, force: true });

cpSync(standalone, staging, { recursive: true });
// The standalone output expects static assets and public files next to it.
cpSync(join(frontendDir, 'public'), join(staging, 'public'), { recursive: true });
cpSync(join(frontendDir, '.next', 'static'), join(staging, '.next', 'static'), { recursive: true });

function sizeOf(dir) {
  let total = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) total += sizeOf(full);
    else total += statSync(full).size;
  }
  return total;
}

console.log(`prepare-frontend: staged ${(sizeOf(staging) / 1024 / 1024).toFixed(1)} MB -> ${staging}`);
