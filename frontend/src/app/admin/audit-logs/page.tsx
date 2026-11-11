'use client';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';
import { Button } from '@/components/ui/primitives';
import { auditApi } from '@/services/audit';
import { apiErrorMessage, shouldRetryQuery, retryDelayMs } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-IN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

function actionColor(action: string): string {
  const a = action.toUpperCase();
  if (a.includes('DELET') || a.includes('REVOK') || a.includes('REVERSAL') || a.includes('FAILED')) {
    return 'text-red-600';
  }
  if (a.includes('CREAT') || a.includes('LOGIN') || a.includes('ISSU')) {
    return 'text-green-600';
  }
  if (a.includes('UPDAT') || a.includes('CHANG') || a.includes('RESET')) {
    return 'text-amber-600';
  }
  return 'text-stone-600';
}

function actionLabel(action: string): string {
  return action
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

function truncate(s: string | null | undefined, n = 28): string {
  if (!s) return '—';
  return s.length > n ? s.slice(0, n) + '…' : s;
}

type AuditEntry = {
  id: string;
  actor_user_id: string | null;
  actor_username: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  metadata: { [key: string]: unknown } | null;
  ip_address: string | null;
  created_at: string;
};

function MetadataDialog({ entry, open, onClose }: { entry: AuditEntry; open: boolean; onClose: () => void }) {
  if (!open) return null;
  const meta = entry.metadata ?? {};
  const rows = meta ? Object.entries(meta) : [];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true" aria-label="Audit record details">
      <div className="fixed inset-0 bg-stone-900/20 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg mx-4 p-2">
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Audit Record Details</h2>
            <Button type="button" onClick={onClose} className="text-xs">Close</Button>
          </div>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between border-b border-stone-200 pb-2">
              <dt className="text-stone-500">ID</dt>
              <dd className="font-mono text-xs">{entry.id}</dd>
            </div>
            <div className="flex justify-between border-b border-stone-200 pb-2">
              <dt className="text-stone-500">Action</dt>
              <dd className={`font-semibold ${actionColor(entry.action)}`}>{actionLabel(entry.action)}</dd>
            </div>
            <div className="flex justify-between border-b border-stone-200 pb-2">
              <dt className="text-stone-500">Actor</dt>
              <dd>{entry.actor_username ?? entry.actor_user_id ?? 'System'}</dd>
            </div>
            <div className="flex justify-between border-b border-stone-200 pb-2">
              <dt className="text-stone-500">Resource Type</dt>
              <dd>{entry.resource_type}</dd>
            </div>
            <div className="flex justify-between border-b border-stone-200 pb-2">
              <dt className="text-stone-500">Resource ID</dt>
              <dd className="font-mono text-xs">{entry.resource_id}</dd>
            </div>
            <div className="flex justify-between border-b border-stone-200 pb-2">
              <dt className="text-stone-500">Timestamp</dt>
              <dd>{formatDate(entry.created_at)}</dd>
            </div>
            <div className="flex justify-between border-b border-stone-200 pb-2">
              <dt className="text-stone-500">IP Address</dt>
              <dd>{entry.ip_address ?? '—'}</dd>
            </div>
            {rows.length > 0 ? (
              <>
                <div className="flex justify-between border-b border-stone-200 pb-2">
                  <dt className="text-stone-500">Metadata</dt>
                  <dd className="text-xs font-mono text-stone-600">Sanitised by backend</dd>
                </div>
                <div className="bg-stone-50 rounded p-3 text-xs font-mono leading-relaxed text-stone-700 overflow-x-auto">
                  {rows.map(([key, value]) => (
                    <div key={key} className="flex justify-between mb-1">
                      <span className="text-stone-500">{key}:</span>
                      <span>{JSON.stringify(value)}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-xs text-stone-400 mt-2">No metadata recorded.</p>
            )}
          </dl>
        </Card>
      </div>
    </div>
  );
}

export default function AuditLogsPage() {
  const { me } = useAuthStore();
  const permissions = me?.permissions ?? [];
  const canReadAudit = permissions.includes('audit.read');

  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');
  const [actorFilter, setActorFilter] = useState<string>('');
  const [actionFilter, setActionFilter] = useState<string>('');
  const [resourceTypeFilter, setResourceTypeFilter] = useState<string>('');
  const [resourceIdFilter, setResourceIdFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [filterErr, setFilterErr] = useState('');
  const [selectedEntry, setSelectedEntry] = useState<AuditEntry | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  const query = useQuery({
    queryKey: ['audit-logs', fromDate, toDate, actorFilter, actionFilter, resourceTypeFilter, resourceIdFilter, page],
    queryFn: () =>
      auditApi.list(
        fromDate || undefined,
        toDate || undefined,
        actorFilter || undefined,
        actionFilter || undefined,
        resourceTypeFilter || undefined,
        resourceIdFilter || undefined,
        page,
        50,
      ),
    enabled: canReadAudit,
    retry: shouldRetryQuery,
    retryDelay: retryDelayMs,
  });

  const anyLoading = query.isLoading;
  const anyError = query.isError;

  if (!canReadAudit) {
    return (
      <div className="mt-8">
        <h1 className="text-2xl font-semibold tracking-tight">Audit Logs</h1>
        <Card className="mt-4 p-4 rounded-md border border-red-200 bg-red-50">
          <p className="text-sm text-red-800">
            You do not have permission to view audit logs. Access requires the
            <code>audit.read</code> permission (ADMIN only).
          </p>
        </Card>
      </div>
    );
  }

  if (anyLoading) return <Spinner />;

  if (anyError) {
    return (
      <div className="mt-8">
        <h1 className="text-2xl font-semibold tracking-tight">Audit Logs</h1>
        <Err message={apiErrorMessage(query.error ?? new Error('Unknown error'))} />
        <Button type="button" onClick={() => query.refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const data = query.data;
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? 50;
  const totalPages = Math.ceil(total / pageSize);

  function handleApply() {
    if (fromDate && toDate && fromDate > toDate) {
      setFilterErr('From date must be on or before to date.');
      return;
    }
    setFilterErr('');
    setPage(1);
  }

  function handleReset() {
    setFromDate('');
    setToDate('');
    setActorFilter('');
    setActionFilter('');
    setResourceTypeFilter('');
    setResourceIdFilter('');
    setFilterErr('');
    setPage(1);
  }

  const periodLabel =
    fromDate && toDate ? `${fromDate} → ${toDate}` : fromDate ? `from ${fromDate}` : toDate ? `until ${toDate}` : 'All time';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audit Logs</h1>
          <p className="text-sm text-stone-500">
            Append-only administrative action trail for the period: <span className="font-medium">{periodLabel}</span>
          </p>
        </div>
      </div>

      {filterErr ? <Err message={filterErr} /> : null}

      {/* Filters */}
      <Card className="mt-2">
        <div className="p-4">
          <form onSubmit={(e) => { e.preventDefault(); handleApply(); }} className="flex flex-wrap gap-3 items-end" data-testid="filter-form">
            <Field label="From date">
              <Input data-testid="filter-from-date" type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
            </Field>
            <Field label="To date">
              <Input data-testid="filter-to-date" type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
            </Field>
            <Field label="Actor">
              <Input data-testid="filter-actor" value={actorFilter} onChange={(e) => setActorFilter(e.target.value)} placeholder="Username…" />
            </Field>
            <Field label="Action">
              <Input data-testid="filter-action" value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} placeholder="e.g. BOOKING_CREATED" />
            </Field>
            <Field label="Resource type">
              <Input data-testid="filter-resource-type" value={resourceTypeFilter} onChange={(e) => setResourceTypeFilter(e.target.value)} placeholder="e.g. booking" />
            </Field>
            <Field label="Resource ID">
              <Input data-testid="filter-resource-id" value={resourceIdFilter} onChange={(e) => setResourceIdFilter(e.target.value)} placeholder="e.g. b1" />
            </Field>
            <Button type="submit" data-testid="btn-apply-filter">Apply filter</Button>
            <Button type="button" onClick={handleReset} className="bg-stone-200 text-stone-800 hover:bg-stone-300" data-testid="btn-reset-filter">
              Reset filters
            </Button>
          </form>
        </div>
      </Card>

      {/* Audit table */}
      <Card>
        <div className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium">Audit trail</h2>
            <span className="text-xs text-stone-500">{total} record{total !== 1 ? 's' : ''}</span>
          </div>
          {items.length === 0 ? (
            <Empty title="No audit entries" hint="No administrative actions recorded for the selected period." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-stone-200 text-left text-xs text-stone-500">
                    <th className="pb-3 w-24">Timestamp</th>
                    <th className="pb-3 w-24">Actor</th>
                    <th className="pb-3 w-32">Action</th>
                    <th className="pb-3">Resource</th>
                    <th className="pb-3 text-right w-20">Resource ID</th>
                    <th className="pb-3 text-right w-16">View</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((entry: AuditEntry) => (
                    <tr key={entry.id} className="border-b border-stone-100 hover:bg-stone-50/50 group">
                      <td className="py-3 font-mono text-xs">{formatDate(entry.created_at)}</td>
                      <td className="py-3">{entry.actor_username ?? entry.actor_user_id ?? 'System'}</td>
                      <td className="py-3 font-semibold text-xs">
                        <span className={`px-1.5 py-0.5 rounded ${actionColor(entry.action)}`}>
                          {actionLabel(entry.action)}
                        </span>
                      </td>
                      <td className="py-3 font-mono text-xs">{entry.resource_type}</td>
                      <td className="py-3 text-right font-mono text-xs">{truncate(entry.resource_id)}</td>
                      <td className="py-3 text-right">
                        <Button
                          type="button"
                          onClick={() => { setSelectedEntry(entry); setShowDetails(true); }}
                        >
                          Details
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > 0 && (
            <div className="mt-4 flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  data-testid="btn-prev-page"
                >
                  Previous
                </Button>
                <span className="text-stone-500">Page {page} of {totalPages}</span>
                <Button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages || totalPages === 0}
                  data-testid="btn-next-page"
                >
                  Next
                </Button>
              </div>
              <div className="text-stone-500">
                Showing {items.length} of {total}
              </div>
            </div>
          )}
        </div>
      </Card>

      {selectedEntry && (
        <MetadataDialog
          entry={selectedEntry}
          open={showDetails}
          onClose={() => setShowDetails(false)}
        />
      )}
    </div>
  );
}
