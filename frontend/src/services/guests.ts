import { api } from '@/lib/api';
import type { Guest } from '@/types';

const get = async <T>(p: string) => (await api.get<T>(p)).data;
const post = async <T>(p: string, b: unknown) => (await api.post<T>(p, b)).data;
const patch = async <T>(p: string, b: unknown) => (await api.patch<T>(p, b)).data;

export interface GuestList { items: Guest[]; total: number; page: number; page_size: number; }

export const guestsApi = {
  list: (q?: string, page = 1, page_size = 20, include_inactive = false) =>
    get<GuestList>(`/guests?q=${encodeURIComponent(q ?? '')}&page=${page}&page_size=${page_size}&include_inactive=${include_inactive}`),
  get: (id: string) => get<Guest>(`/guests/${id}`),
  create: (b: unknown) => post<Guest>('/guests', b),
  update: (id: string, b: unknown) => patch<Guest>(`/guests/${id}`, b),
  deactivate: (id: string) => post<Guest>(`/guests/${id}/deactivate`, {}),
};
