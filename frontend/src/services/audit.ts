import type {
  AuditLogListResponse,
} from '@/types';
import { api } from '@/lib/api';

const get = async <T>(p: string) => (await api.get<T>(p)).data;

/**
 * Audit log API — ADMIN-only (audit.read).
 * All read-only; no write endpoints exist by design (append-only).
 */
export const auditApi = {
  list: (
    from_date?: string,
    to_date?: string,
    actor?: string,
    action?: string,
    resource_type?: string,
    resource_id?: string,
    page = 1,
    page_size = 50,
  ) => {
    const qs: string[] = [];
    if (from_date) qs.push(`from_date=${encodeURIComponent(from_date)}`);
    if (to_date) qs.push(`to_date=${encodeURIComponent(to_date)}`);
    if (actor) qs.push(`actor=${encodeURIComponent(actor)}`);
    if (action) qs.push(`action=${encodeURIComponent(action)}`);
    if (resource_type) qs.push(`resource_type=${encodeURIComponent(resource_type)}`);
    if (resource_id) qs.push(`resource_id=${encodeURIComponent(resource_id)}`);
    qs.push(`page=${page}`);
    qs.push(`page_size=${page_size}`);
    return get<AuditLogListResponse>(`/audit-logs?${qs.join('&')}`);
  },
};
