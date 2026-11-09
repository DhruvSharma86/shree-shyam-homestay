import { describe, it, expect } from 'vitest';
import axios from 'axios';
import {
  classifyError,
  mutationErrorMessage,
  retryDelayMs,
  shouldRetryQuery,
} from '@/lib/api';

function axiosErr(opts: {
  status?: number | null;
  code?: string;
  message?: string;
  data?: unknown;
}) {
  const e = new Error(opts.message ?? 'boom') as Error & {
    isAxiosError?: boolean;
    code?: string;
    response: unknown;
    config: object;
    request: object;
  };
  e.isAxiosError = true;
  e.code = opts.code;
  e.config = {};
  e.request = {};
  e.response =
    opts.status == null
      ? undefined
      : { status: opts.status, data: opts.data ?? { error: { message: 'server detail' } } };
  return e;
}

describe('classifyError', () => {
  it('maps network failures without a response', () => {
    const { kind } = classifyError(axiosErr({ message: 'Network Error' }));
    expect(kind).toBe('network');
  });

  it('maps timeouts distinctly from network', () => {
    const { kind } = classifyError(axiosErr({ code: 'ECONNABORTED', message: 'timeout of 15000ms exceeded' }));
    expect(kind).toBe('timeout');
  });

  it('maps 404/401/403/422/409 and 5xx distinctly', () => {
    expect(classifyError(axiosErr({ status: 404 })).kind).toBe('invalid');
    expect(classifyError(axiosErr({ status: 401 })).kind).toBe('auth');
    expect(classifyError(axiosErr({ status: 403 })).kind).toBe('forbidden');
    expect(classifyError(axiosErr({ status: 422 })).kind).toBe('validation');
    expect(classifyError(axiosErr({ status: 409 })).kind).toBe('conflict');
    expect(classifyError(axiosErr({ status: 500 })).kind).toBe('server');
    expect(classifyError(axiosErr({ status: 503 })).kind).toBe('server');
    expect(classifyError(axiosErr({ status: 429 })).kind).toBe('server');
    expect(classifyError(axiosErr({ status: 400 })).kind).toBe('generic');
  });
});

describe('shouldRetryQuery', () => {
  it('retries only transient failures, at most twice', () => {
    expect(shouldRetryQuery(0, axiosErr({ message: 'Network Error' }))).toBe(true);
    expect(shouldRetryQuery(1, axiosErr({ code: 'ECONNABORTED', message: 'timeout' }))).toBe(true);
    expect(shouldRetryQuery(2, axiosErr({ message: 'Network Error' }))).toBe(false);
    expect(shouldRetryQuery(0, axiosErr({ status: 500 }))).toBe(true);
  });

  it('never retries permanent outcomes (404/401/403/422)', () => {
    expect(shouldRetryQuery(0, axiosErr({ status: 404 }))).toBe(false);
    expect(shouldRetryQuery(0, axiosErr({ status: 401 }))).toBe(false);
    expect(shouldRetryQuery(0, axiosErr({ status: 403 }))).toBe(false);
    expect(shouldRetryQuery(0, axiosErr({ status: 422 }))).toBe(false);
  });

  it('backs off exponentially (1s, 2s, capped 5s)', () => {
    expect(retryDelayMs(0)).toBe(1000);
    expect(retryDelayMs(1)).toBe(2000);
    expect(retryDelayMs(5)).toBe(5000);
  });
});

describe('mutationErrorMessage', () => {
  it('guides staff to verify state on timeout/network (unknown outcome)', () => {
    for (const err of [axiosErr({ message: 'Network Error' }), axiosErr({ code: 'ECONNABORTED', message: 'timeout' })]) {
      const msg = mutationErrorMessage(err);
      expect(msg).toMatch(/may have recorded/i);
      expect(msg).toMatch(/Check the current booking state/i);
      expect(msg).not.toMatch(/server detail/);
    }
  });

  it('surfaces business-rule messages for 409/422', () => {
    const msg = mutationErrorMessage(
      axiosErr({ status: 422, data: { error: { message: 'Payment does not cover the first night.' } } }),
    );
    expect(msg).toBe('Payment does not cover the first night.');
  });
});

describe('guestTimeout client', () => {
  it('uses a 15s timeout (not excessive)', async () => {
    const { REQUEST_TIMEOUT_MS } = await import('@/lib/api');
    expect(REQUEST_TIMEOUT_MS).toBe(15000);
  });
});

// Silence unused import warning for axios (used in helper typings).
void axios.isAxiosError;
