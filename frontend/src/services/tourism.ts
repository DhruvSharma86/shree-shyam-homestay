import type { BookingDetail, BookingList, CheckInResult, LocalInfoAdmin, TourismPackageAdmin } from '@/types';
import { api } from '@/lib/api';

const get = async <T>(p: string) => (await api.get<T>(p)).data;
const post = async <T>(p: string, b: unknown) => (await api.post<T>(p, b)).data;
const patch = async <T>(p: string, b: unknown) => (await api.patch<T>(p, b)).data;

export const tourismApi = {
  packages: () => get<TourismPackageAdmin[]>('/admin/tour-packages'),
  createPackage: (b: unknown) => post<TourismPackageAdmin>('/admin/tour-packages', b),
  updatePackage: (id: string, b: unknown) => patch<TourismPackageAdmin>(`/admin/tour-packages/${id}`, b),
  localInfo: () => get<LocalInfoAdmin[]>('/admin/local-info'),
  createLocalInfo: (b: unknown) => post<LocalInfoAdmin>('/admin/local-info', b),
  updateLocalInfo: (id: string, b: unknown) => patch<LocalInfoAdmin>(`/admin/local-info/${id}`, b),
};

export const bookingsApi = {
  list: (page = 1, page_size = 50) => get<BookingList>(`/bookings?page=${page}&page_size=${page_size}`),
  get: (id: string) => get<BookingDetail>(`/bookings/${id}`),
  recordCheckInPayment: (id: string, b: unknown) => post<unknown>(`/bookings/${id}/payments`, b),
  checkIn: (id: string) => post<CheckInResult>(`/bookings/${id}/check-in`, {}),
  receipt: (id: string) => get<{ receipt_ref: string; kind: string; content_hash: string }>(`/bookings/${id}/receipt`),
  rotatePortal: (id: string) =>
    post<{ booking_id: string; portal_access_token: string }>(`/guest-portal/admin-rotate/${id}`, {}),
  revokePortal: (id: string) => post<unknown>(`/guest-portal/admin-revoke/${id}`, {}),
};

export async function downloadStaffReceipt(bookingId: string): Promise<Blob> {
  const res = await api.get(`/bookings/${bookingId}/receipt/download`, { responseType: 'blob' });
  return res.data as Blob;
}
