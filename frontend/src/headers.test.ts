import { describe, it, expect } from 'vitest';
import nextConfig from '../next.config';

describe('security headers config (Priority 3)', () => {
  it('serves no-store/noindex headers for guest routes', async () => {
    const rules = await nextConfig.headers?.();
    expect(rules).toBeDefined();
    const guest = rules?.find((r) => r.source === '/guest/:path*');
    expect(guest).toBeDefined();
    const byKey = Object.fromEntries(guest!.headers.map((h) => [h.key, h.value]));
    expect(byKey['Cache-Control']).toBe('no-store, private');
    expect(byKey['X-Robots-Tag']).toBe('noindex, nofollow');
    expect(byKey['Referrer-Policy']).toBe('no-referrer');
    expect(byKey['X-Content-Type-Options']).toBe('nosniff');
    expect(byKey['X-Frame-Options']).toBe('DENY');
  });

  it('sets baseline protections on all routes', async () => {
    const rules = await nextConfig.headers?.();
    const global = rules?.find((r) => r.source === '/:path*');
    expect(global).toBeDefined();
    const byKey = Object.fromEntries(global!.headers.map((h) => [h.key, h.value]));
    expect(byKey['X-Content-Type-Options']).toBe('nosniff');
    expect(byKey['X-Frame-Options']).toBe('DENY');
    expect(byKey['Referrer-Policy']).toBe('no-referrer');
  });
});
