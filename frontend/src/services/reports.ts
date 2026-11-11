import type {
  BookingsSummaryResponse,
  CollectionReportResponse,
  FinancialSummaryResponse,
  MethodReportResponse,
  OccupancyResponse,
  OutstandingReportResponse,
  ReconciliationResponse,
  ReversalsReportResponse,
} from '@/types';
import { api } from '@/lib/api';

const get = async <T>(p: string) => (await api.get<T>(p)).data;

/**
 * Report API — all endpoints are ADMIN-only (REPORTS_FINANCIAL_READ).
 * All figures are backend-calculated; the frontend never computes
 * authoritative financial totals independently.
 */
export const reportsApi = {
  financialSummary: (from_date?: string, to_date?: string) =>
    get<FinancialSummaryResponse>(
      `/reports/financial/summary${_queryString({ from_date, to_date })}`,
    ),

  collections: (from_date?: string, to_date?: string) =>
    get<CollectionReportResponse>(
      `/reports/financial/collections${_queryString({ from_date, to_date })}`,
    ),

  collectionsExport: (from_date?: string, to_date?: string) =>
    api.get(`/reports/financial/collections/export.csv${_queryString({ from_date, to_date })}`, {
      responseType: 'blob',
    }),

  paymentMethods: (from_date?: string, to_date?: string) =>
    get<MethodReportResponse>(
      `/reports/financial/payment-methods${_queryString({ from_date, to_date })}`,
    ),

  outstanding: (page = 1, page_size = 50) =>
    get<OutstandingReportResponse>(
      `/reports/financial/outstanding?page=${page}&page_size=${page_size}`,
    ),

  outstandingExport: () =>
    api.get('/reports/financial/outstanding/export.csv', { responseType: 'blob' }),

  reconciliation: (from_date?: string, to_date?: string) =>
    get<ReconciliationResponse>(
      `/reports/financial/reconciliation${_queryString({ from_date, to_date })}`,
    ),

  reversals: (from_date?: string, to_date?: string, page = 1, page_size = 50) =>
    get<ReversalsReportResponse>(
      `/reports/financial/reversals?page=${page}&page_size=${page_size}${_queryString({ from_date, to_date })}`,
    ),

  bookingsSummary: (from_date?: string, to_date?: string) =>
    get<BookingsSummaryResponse>(
      `/reports/bookings/summary${_queryString({ from_date, to_date })}`,
    ),

  occupancy: (from_date?: string, to_date?: string) =>
    get<OccupancyResponse>(
      `/reports/bookings/occupancy${_queryString({ from_date, to_date })}`,
    ),
};

function _queryString(params: { from_date?: string | undefined; to_date?: string | undefined }): string {
  const qs: string[] = [];
  if (params.from_date) qs.push(`from_date=${encodeURIComponent(params.from_date)}`);
  if (params.to_date) qs.push(`to_date=${encodeURIComponent(params.to_date)}`);
  return qs.length ? `?${qs.join('&')}` : '';
}

export async function downloadCollectionsCsv(from_date?: string, to_date?: string): Promise<Blob> {
  const res = await reportsApi.collectionsExport(from_date, to_date);
  return res.data as Blob;
}

export async function downloadOutstandingCsv(): Promise<Blob> {
  const res = await reportsApi.outstandingExport();
  return res.data as Blob;
}
