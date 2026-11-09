import axios from 'axios';
import type {
  GuestCab,
  GuestMenu,
  GuestOverview,
  GuestReceiptInfo,
  GuestTourism,
  GuestWifi,
} from '@/types';

const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const prefix = process.env.NEXT_PUBLIC_API_V1 ?? '/api/v1';

// Guest endpoints are bearer-link gated, not session gated: this client
// deliberately sends NO cookies and NEVER stores the token.
export const guestApi = axios.create({ baseURL: `${base}${prefix}` });

const p = (token: string) => `/guest-portal/${token}`;
const get = async <T>(path: string) => (await guestApi.get<T>(path)).data;

export const guestPortalApi = {
  overview: (token: string) => get<GuestOverview>(`${p(token)}/overview`),
  menu: (token: string) => get<GuestMenu>(`${p(token)}/menu`),
  cab: (token: string) => get<GuestCab>(`${p(token)}/cab`),
  wifi: (token: string) => get<GuestWifi>(`${p(token)}/wifi`),
  tourism: (token: string) => get<GuestTourism>(`${p(token)}/tourism`),
  receipt: (token: string) => get<GuestReceiptInfo>(`${p(token)}/receipt`),
  receiptDownloadUrl: (token: string) => `${base}${prefix}/guest-portal/${token}/receipt/download`,
};

export async function downloadReceipt(token: string): Promise<Blob> {
  const res = await guestApi.get(`${p(token)}/receipt/download`, { responseType: 'blob' });
  return res.data as Blob;
}
