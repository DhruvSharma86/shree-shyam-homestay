'use client';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, Empty, Err, Field, Input, RetryButton, Spinner } from '@/components/ui/primitives';
import { reportsApi, downloadCollectionsCsv, downloadOutstandingCsv } from '@/services/reports';
import { apiErrorMessage, mutationErrorMessage, shouldRetryQuery, retryDelayMs } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { Button } from '@/components/ui/primitives';

// Simple currency formatter
function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(v);
}

// Simple bar chart rendered with CSS (no external chart dependency)
function SimpleBarChart({
  data,
  valueLabel,
}: {
  data: { label: string; value: number }[];
  valueLabel: (v: number) => string;
}) {
  const max = Math.max(0, ...data.map((d) => d.value));
  const showEmpty = data.length === 0 || max === 0;
  return (
    <div className="w-full h-full flex flex-col">
      <div className="flex-1 flex items-end gap-1 bg-stone-50 rounded-lg border border-stone-200 p-3 relative overflow-hidden aria-busy={showEmpty ? 'true' : 'false'}" aria-label={showEmpty ? 'No data available for the selected period' : `Bar chart showing ${valueLabel} over time`}>
        {showEmpty ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-stone-400 text-sm">
            <p>No data for selected period</p>
          </div>
        ) : (
          data.map((d) => {
            const pct = max > 0 ? (d.value / max) * 100 : 0;
            return (
              <div key={d.label} className="flex flex-col items-center gap-1 w-full">
                <div
                  className="w-full bg-stone-900 rounded-t-sm transition-all duration-300"
                  style={{ height: `${Math.max(pct, 3)}%` }}
                  title={`${d.label}: ${valueLabel(d.value)}`}
                ></div>
                <span className="text-xs text-stone-500 leading-none">{d.label}</span>
              </div>
            );
          })
        )}
      </div>
      <div className="mt-2 flex justify-between text-xs text-stone-500">
        <span>Min</span>
        <span>Max</span>
      </div>
    </div>
  );
}

function CurrencyCard({ label, value, href, isNegative = false }: { label: string; value: number | null | undefined; href?: string; isNegative?: boolean }) {
  const formatted = money(value);
  const isZero = value === 0 || value === null || value === undefined;
  return (
    <Card className={isZero ? 'bg-stone-50 border-stone-200' : ''}>
      <p className={`text-sm font-medium text-stone-500 ${isNegative ? 'text-red-600' : ''}`}>{label}</p>
      <p className={`text-2xl font-semibold ${isNegative ? 'text-red-600' : 'text-stone-800'}`}>{formatted}</p>
      {href ? (
        <a href={href} className="mt-3 block text-xs text-stone-600 hover:text-stone-900 underline">
          View details →
        </a>
      ) : null}
    </Card>
  );
}

export default function ReportsPage() {
  const { me } = useAuthStore();
  const permissions = me?.permissions ?? [];
  const canReadFinancial = permissions.includes('reports.financial.read');
  const isAdmin = permissions.includes('users.manage') || me?.user.role === 'ADMIN';

  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');
  const [filterErr, setFilterErr] = useState('');

  const summary = useQuery({
    queryKey: ['reports', 'financial-summary', fromDate, toDate],
    queryFn: () => reportsApi.financialSummary(fromDate || undefined, toDate || undefined),
    enabled: canReadFinancial && (!fromDate || !toDate || fromDate <= toDate),
    retry: shouldRetryQuery,
    retryDelay: retryDelayMs,
  });

  const collections = useQuery({
    queryKey: ['reports', 'collections', fromDate, toDate],
    queryFn: () => reportsApi.collections(fromDate || undefined, toDate || undefined),
    enabled: canReadFinancial && (!fromDate || !toDate || fromDate <= toDate),
    retry: shouldRetryQuery,
    retryDelay: retryDelayMs,
  });

  const methods = useQuery({
    queryKey: ['reports', 'payment-methods', fromDate, toDate],
    queryFn: () => reportsApi.paymentMethods(fromDate || undefined, toDate || undefined),
    enabled: canReadFinancial && (!fromDate || !toDate || fromDate <= toDate),
    retry: shouldRetryQuery,
    retryDelay: retryDelayMs,
  });

  const bookings = useQuery({
    queryKey: ['reports', 'bookings-summary', fromDate, toDate],
    queryFn: () => reportsApi.bookingsSummary(fromDate || undefined, toDate || undefined),
    enabled: canReadFinancial && (!fromDate || !toDate || fromDate <= toDate),
    retry: shouldRetryQuery,
    retryDelay: retryDelayMs,
  });

  const occupancy = useQuery({
    queryKey: ['reports', 'occupancy', fromDate, toDate],
    queryFn: () => reportsApi.occupancy(fromDate || undefined, toDate || undefined),
    enabled: canReadFinancial && (!fromDate || !toDate || fromDate <= toDate),
    retry: shouldRetryQuery,
    retryDelay: retryDelayMs,
  });

  const outstanding = useQuery({
    queryKey: ['reports', 'outstanding'],
    queryFn: () => reportsApi.outstanding(),
    enabled: canReadFinancial,
    retry: shouldRetryQuery,
    retryDelay: retryDelayMs,
  });

  const reversals = useQuery({
    queryKey: ['reports', 'reversals', fromDate, toDate],
    queryFn: () => reportsApi.reversals(fromDate || undefined, toDate || undefined),
    enabled: canReadFinancial && (!fromDate || !toDate || fromDate <= toDate),
    retry: shouldRetryQuery,
    retryDelay: retryDelayMs,
  });

  const reconciliation = useQuery({
    queryKey: ['reports', 'reconciliation', fromDate, toDate],
    queryFn: () => reportsApi.reconciliation(fromDate || undefined, toDate || undefined),
    enabled: canReadFinancial && (!fromDate || !toDate || fromDate <= toDate),
    retry: shouldRetryQuery,
    retryDelay: retryDelayMs,
  });

  const anyLoading = [summary, collections, methods, bookings, occupancy, outstanding, reversals, reconciliation].some((q) => q.isLoading);
  const anyError = [summary, collections, methods, bookings, occupancy, outstanding, reversals, reconciliation].some((q) => q.isError);

  if (!canReadFinancial) {
    return (
      <div className="mt-8">
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <Card className="mt-4 p-4 rounded-md border border-red-200 bg-red-50">
          <p className="text-sm text-red-800">
            You do not have permission to view financial reports. Reports require the
            <code>reports.financial.read</code> permission (ADMIN only).
          </p>
        </Card>
      </div>
    );
  }

  if (anyLoading) return <Spinner />;

  if (anyError) {
    const firstError = [summary, collections, methods, bookings, occupancy, outstanding, reversals, reconciliation].find((q) => q.isError);
    return (
      <div className="mt-8">
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <Err message={apiErrorMessage(firstError?.error ?? new Error('Unknown error'))} />
        <Button type="button" onClick={() => {
          [summary, collections, methods, bookings, occupancy, outstanding, reversals, reconciliation].forEach((q) => q.refetch());
        }}>
          Retry
        </Button>
      </div>
    );
  }

  // Collections data for chart (last 14 days with data)
  const collectionRows = collections.data?.rows ?? [];
  const chartData = collectionRows
    .filter((r) => r.stage !== 'REVERSAL' || true)
    .map((r) => ({ label: r.date, value: r.net_total }))
    .slice(-14);

  // Payment methods for mini bar chart
  const methodRows = methods.data?.rows ?? [];
  const methodChartData = methodRows.map((m) => ({ label: m.method, value: m.net_total }));

  // Outstanding table rows
  const outstandingRows = outstanding.data?.rows ?? [];

  // Reversals table rows
  const reversalItems = reversals.data?.items ?? [];

  function handleApply() {
    if (fromDate && toDate && fromDate > toDate) {
      setFilterErr('From date must be on or before to date.');
      return;
    }
    setFilterErr('');
  }

  function handleDownloadCollections() {
    void downloadCollectionsCsv(fromDate || undefined, toDate || undefined).catch((e) => {
      setFilterErr(mutationErrorMessage(e));
    });
  }

  function handleDownloadOutstanding() {
    void downloadOutstandingCsv().catch((e) => {
      setFilterErr(mutationErrorMessage(e));
    });
  }

  const periodLabel =
    fromDate && toDate ? `${fromDate} → ${toDate}` : fromDate ? `from ${fromDate}` : toDate ? `until ${toDate}` : 'All time';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Reports &amp; Analytics</h1>
          <p className="text-sm text-stone-500">All figures are backend-calculated for the period: <span className="font-medium">{periodLabel}</span></p>
        </div>
        {!isAdmin && (
          <p className="text-xs text-stone-500">ADMIN-only: financial reports</p>
        )}
      </div>

      {filterErr ? <Err message={filterErr} /> : null}

      {/* Filters */}
      <Card className="mt-2">
        <div className="p-4">
          <form onSubmit={(e) => { e.preventDefault(); handleApply(); }} className="flex flex-wrap gap-3 items-end">
            <Field label="From date">
              <Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
            </Field>
            <Field label="To date">
              <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
            </Field>
            <Button type="submit" data-testid="btn-apply-filter">Apply filter</Button>
            <Button type="button" onClick={() => { setFromDate(''); setToDate(''); setFilterErr(''); }} className="bg-stone-200 text-stone-800 hover:bg-stone-300" data-testid="btn-clear-filter">
              Clear
            </Button>
          </form>
        </div>
      </Card>

      {/* Financial Summary Cards */}
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <CurrencyCard label="Room charges" value={summary.data?.room_charges ?? null} />
        <CurrencyCard label="Additional charges" value={summary.data?.additional_charges ?? null} />
        <CurrencyCard label="Discounts" value={summary.data?.discounts ?? null} isNegative />
        <CurrencyCard label="Gross charges" value={summary.data?.gross_charges ?? null} />
        <CurrencyCard label="Net payments" value={summary.data?.net_payments ?? null} />
        <CurrencyCard label="Outstanding" value={summary.data?.outstanding ?? null} isNegative />
      </div>

      {/* Reconciliation */}
      <Card>
        <div className="p-4">
          <h2 className="font-medium mb-3">Period Reconciliation</h2>
          <div className="grid gap-2 sm:grid-cols-4 text-sm">
            <div><p className="text-stone-500">Charge entries</p><p className="font-semibold">{money(reconciliation.data?.charge_entries ?? null)}</p></div>
            <div><p className="text-stone-500">Original payments</p><p className="font-semibold">{money(reconciliation.data?.original_payments ?? null)}</p></div>
            <div><p className="text-stone-500">Reversal payments</p><p className="font-semibold text-red-600">{money(reconciliation.data?.reversal_payments ?? null)}</p></div>
            <div><p className="text-stone-500">Net payments</p><p className="font-semibold">{money(reconciliation.data?.net_payments ?? null)}</p></div>
            <div><p className="text-stone-500">Outstanding in period</p><p className="font-semibold">{money(reconciliation.data?.outstanding_in_period ?? null)}</p></div>
            <div><p className="text-stone-500">Credit in period</p><p className="font-semibold text-green-600">{money(reconciliation.data?.credit_in_period ?? null)}</p></div>
          </div>
          <div className="mt-3 text-xs text-stone-500">
            Entries: {reconciliation.data?.entry_count ?? 0} &bull; Payments: {reconciliation.data?.payment_count ?? 0} &bull; Reversals: {reconciliation.data?.reversal_count ?? 0}
          </div>
        </div>
      </Card>

      {/* Collections chart + Payment methods */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <div className="p-4">
            <h2 className="font-medium mb-3">Collections Over Time</h2>
            <SimpleBarChart
              data={chartData}
              valueLabel={(v) => money(v)}
            />
            <div className="mt-3 text-sm text-stone-600">
              Original total: {money(collections.data?.original_total ?? null)} &bull;
              Reversal total: {money(collections.data?.reversal_total ?? null)} &bull;
              Net total: {money(collections.data?.net_total ?? null)}
            </div>
            <div className="mt-3 flex gap-2">
              <Button type="button" onClick={handleDownloadCollections}>
                Download CSV
              </Button>
              {collections.isError ? (
                <RetryButton onRetry={() => collections.refetch()} label="Retry collections" />
              ) : null}
            </div>
          </div>
        </Card>
        <Card>
          <div className="p-4">
            <h2 className="font-medium mb-3">Payment Method Breakdown</h2>
            <SimpleBarChart
              data={methodChartData}
              valueLabel={(v) => money(v)}
            />
            <div className="mt-3 text-sm text-stone-600">
              Original total: {money(methods.data?.original_total ?? null)} &bull;
              Reversal total: {money(methods.data?.reversal_total ?? null)} &bull;
              Net total: {money(methods.data?.net_total ?? null)}
            </div>
          </div>
        </Card>
      </div>

      {/* Bookings summary + Occupancy */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <div className="p-4">
            <h2 className="font-medium mb-3">Bookings by Status</h2>
            <div className="grid gap-2 sm:grid-cols-2 text-sm">
              <div><p className="text-stone-500">Confirmed</p><p className="font-semibold">{bookings.data?.confirmed ?? 0}</p></div>
              <div><p className="text-stone-500">Checked in</p><p className="font-semibold">{bookings.data?.checked_in ?? 0}</p></div>
              <div><p className="text-stone-500">Checked out</p><p className="font-semibold">{bookings.data?.checked_out ?? 0}</p></div>
              <div><p className="text-stone-500">Cancelled</p><p className="font-semibold text-red-600">{bookings.data?.cancelled ?? 0}</p></div>
            </div>
            <div className="mt-3 text-sm text-stone-600">Total: {bookings.data?.total ?? 0}</div>
          </div>
        </Card>
        <Card>
          <div className="p-4">
            <h2 className="font-medium mb-3">Occupancy</h2>
            <div className="grid gap-2 sm:grid-cols-3 text-sm">
              <div><p className="text-stone-500">Occupied room-nights</p><p className="font-semibold">{occupancy.data?.occupied_room_nights ?? 0}</p></div>
              <div><p className="text-stone-500">Available room-nights</p><p className="font-semibold">{occupancy.data?.available_room_nights ?? 0}</p></div>
              <div><p className="text-stone-500">Occupancy rate</p><p className="font-semibold">{occupancy.data?.occupancy_rate != null ? `${occupancy.data.occupancy_rate}%` : '—'}</p></div>
            </div>
            <div className="mt-3 text-xs text-stone-500">
              Capacity assumes every active AVAILABLE room was available for the whole period.
            </div>
          </div>
        </Card>
      </div>

      {/* Outstanding balances table */}
      <Card>
        <div className="p-4">
          <h2 className="font-medium mb-3">Outstanding Balances</h2>
          <div className="mt-3 text-sm text-stone-600">
            Outstanding total: {money(outstanding.data?.outstanding_total ?? null)} &bull;
            Credit total: {money(outstanding.data?.credit_total ?? null)}
          </div>
          {outstandingRows.length === 0 ? (
            <Empty title="No outstanding balances" hint="All open bookings are settled." />
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-stone-200 text-left text-xs text-stone-500">
                    <th className="pb-2">Booking ref</th>
                    <th className="pb-2">Room</th>
                    <th className="pb-2">Status</th>
                    <th className="pb-2 text-right">Total charges</th>
                    <th className="pb-2 text-right">Net paid</th>
                    <th className="pb-2 text-right">Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {outstandingRows.map((r) => (
                    <tr key={r.booking_id} className="border-b border-stone-100">
                      <td className="py-2">{r.booking_ref}</td>
                      <td className="py-2">{r.room_number}</td>
                      <td className="py-2 text-xs">{r.status}</td>
                      <td className="py-2 text-right">{money(r.total_charges ?? 0)}</td>
                      <td className="py-2 text-right">{money(r.net_paid ?? 0)}</td>
                      <td className={`py-2 text-right font-semibold ${r.balance > 0 ? 'text-red-600' : 'text-green-600'}`}>{money(r.balance ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-3 flex gap-2">
            <Button type="button" onClick={handleDownloadOutstanding}>
              Download CSV
            </Button>
            {outstanding.isError ? (
              <RetryButton onRetry={() => outstanding.refetch()} label="Retry outstanding" />
            ) : null}
          </div>
        </div>
      </Card>

      {/* Reversals table */}
      <Card>
        <div className="p-4">
          <h2 className="font-medium mb-3">Reversals</h2>
          <div className="mt-3 text-sm text-stone-600">
            Charge reversals: {money(reversals.data?.charge_reversal_total ?? null)} &bull;
            Payment reversals: {money(reversals.data?.payment_reversal_total ?? null)}
          </div>
          {reversalItems.length === 0 ? (
            <Empty title="No reversals" hint="No charge or payment reversals in the selected period." />
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-stone-200 text-left text-xs text-stone-500">
                    <th className="pb-2">Kind</th>
                    <th className="pb-2">Booking ref</th>
                    <th className="pb-2 text-right">Amount</th>
                    <th className="pb-2">Reason</th>
                    <th className="pb-2">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {reversalItems.map((r) => (
                    <tr key={r.id} className="border-b border-stone-100">
                      <td className="py-2 text-xs">{r.kind}</td>
                      <td className="py-2">{r.booking_ref}</td>
                      <td className="py-2 text-right">{money(r.amount ?? 0)}</td>
                      <td className="py-2 text-xs">{r.reason ?? '—'}</td>
                      <td className="py-2 text-xs">{r.created_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
