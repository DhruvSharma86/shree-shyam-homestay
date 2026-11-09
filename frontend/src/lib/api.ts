import axios from 'axios';

const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const prefix = process.env.NEXT_PUBLIC_API_V1 ?? '/api/v1';

/** Per-request timeout (ms). Long enough for cold starts, short enough to
 * surface a hung connection instead of spinning forever. */
export const REQUEST_TIMEOUT_MS = 15000;

export const api = axios.create({ baseURL: `${base}${prefix}`, withCredentials: true, timeout: REQUEST_TIMEOUT_MS });

function csrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  const m = document.cookie.match(/(?:^|; )sshs_csrf=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : null;
}

api.interceptors.request.use((cfg) => {
  const m = (cfg.method ?? 'get').toLowerCase();
  if (['post', 'patch', 'put', 'delete'].includes(m)) {
    const t = csrfToken();
    if (t) cfg.headers['X-CSRF-Token'] = t;
  }
  return cfg;
});

/** Classified failure categories — never expose raw backend internals. */
export type ErrorKind =
  | 'network'
  | 'timeout'
  | 'server'
  | 'unavailable'
  | 'invalid'
  | 'auth'
  | 'forbidden'
  | 'validation'
  | 'conflict'
  | 'generic';

export interface ClassifiedError {
  kind: ErrorKind;
  status: number | null;
}

/** Map an unknown error to a safe category (no raw exception text). */
export function classifyError(err: unknown): ClassifiedError {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status ?? null;
    const code = err.code;
    if (!err.response) {
      if (code === 'ECONNABORTED' || code === 'ETIMEDOUT' || /timeout/i.test(err.message)) {
        return { kind: 'timeout', status: null };
      }
      return { kind: 'network', status: null };
    }
    if (status === 401) return { kind: 'auth', status };
    if (status === 403) return { kind: 'forbidden', status };
    if (status === 404) return { kind: 'invalid', status };
    if (status === 409) return { kind: 'conflict', status };
    if (status === 422) return { kind: 'validation', status };
    if (status === 429 || status === 500 || status === 502 || status === 503 || status === 504) {
      return { kind: 'server', status };
    }
    return { kind: 'generic', status };
  }
  return { kind: 'generic', status: null };
}

const KIND_MESSAGES: Record<ErrorKind, string> = {
  network: 'Connection failed. Check your internet connection and try again.',
  timeout: 'The request timed out. Check your connection and try again.',
  server: 'The service is temporarily unavailable. Please try again in a moment.',
  unavailable: 'The service is temporarily unavailable. Please try again in a moment.',
  invalid: 'This link is no longer valid.',
  auth: 'Session expired. Please log in again.',
  forbidden: 'You do not have permission for this action.',
  validation: 'The information you entered is not valid. Please review it and try again.',
  conflict: 'This action conflicts with the current state. Please refresh and try again.',
  generic: 'Request failed. Please try again.',
};

/** User-safe message for a classified error (never a raw backend dump). */
export function classifiedMessage(kind: ErrorKind): string {
  return KIND_MESSAGES[kind];
}

/**
 * Message for failed mutations where the server may already have committed
 * (network/timeout). Never claim certain failure — point at current state.
 */
export function mutationErrorMessage(err: unknown): string {
  const { kind } = classifyError(err);
  if (kind === 'timeout' || kind === 'network') {
    return (
      'The request result could not be confirmed. The server may have recorded it. ' +
      'Check the current booking state before trying again — do not assume it failed.'
    );
  }
  if (kind === 'server') {
    return (
      'The server hit a temporary error. The action may or may not have been recorded. ' +
      'Check the current state, then try again if needed.'
    );
  }
  if (axios.isAxiosError(err)) {
    const d = (err.response?.data as { error?: { message?: string } } | undefined)?.error?.message;
    if (d) return d; // Business-rule message from the known server (generic when unknown)
  }
  return classifiedMessage(kind);
}

/**
 * Bounded retry for safe GET queries: only transient network/timeout/server
 * failures, at most 2 retries (3 attempts total) with exponential backoff.
 * Never retries 404/401/403/422 (permanent outcomes).
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  const { kind } = classifyError(error);
  if (kind !== 'network' && kind !== 'timeout' && kind !== 'server' && kind !== 'unavailable') {
    return false;
  }
  return failureCount < 2;
}

/** Exponential backoff: 1s, 2s (capped at 5s). */
export function retryDelayMs(attemptIndex: number): number {
  return Math.min(1000 * 2 ** attemptIndex, 5000);
}

export function apiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status;
    // Business-rule details from the known API are safe to surface.
    const d = (err.response?.data as { error?: { message?: string } } | undefined)?.error?.message;
    if (d && (status === 409 || status === 422 || status === 400)) return d;
    if (d && status === 401) return 'Session expired. Please log in again.';
    if (d && status === 403) return 'You do not have permission for this action.';
    return classifiedMessage(classifyError(err).kind);
  }
  return err instanceof Error ? err.message : 'Unexpected error.';
}
