import axios from 'axios';

const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const prefix = process.env.NEXT_PUBLIC_API_V1 ?? '/api/v1';

export const api = axios.create({ baseURL: `${base}${prefix}`, withCredentials: true });

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

export function apiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const d = (err.response?.data as { error?: { message?: string } } | undefined)?.error?.message;
    if (d) return d;
    if (err.response?.status === 401) return 'Session expired. Please log in again.';
    if (err.response?.status === 403) return 'You do not have permission for this action.';
    return err.message ?? 'Request failed.';
  }
  return err instanceof Error ? err.message : 'Unexpected error.';
}
