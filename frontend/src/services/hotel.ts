import { api } from '@/lib/api';
import type { CabProvider, HotelInfo, MenuCategory, MenuItem, Restaurant, Room, RoomRate, RoomType, TaxSettings } from '@/types';

const get = async <T>(p: string) => (await api.get<T>(p)).data;
const post = async <T>(p: string, b: unknown) => (await api.post<T>(p, b)).data;
const patch = async <T>(p: string, b: unknown) => (await api.patch<T>(p, b)).data;

export const hotelApi = {
  get: () => get<HotelInfo | null>('/admin/hotel'),
  patch: (b: unknown) => patch<HotelInfo>('/admin/hotel', b),
};
export const roomTypesApi = {
  list: () => get<RoomType[]>('/admin/room-types'),
  create: (b: unknown) => post<RoomType>('/admin/room-types', b),
  update: (id: string, b: unknown) => patch<RoomType>(`/admin/room-types/${id}`, b),
};
export const roomsApi = {
  list: (page = 1, page_size = 100) => get<Room[]>(`/admin/rooms?page=${page}&page_size=${page_size}`),
  create: (b: unknown) => post<Room>('/admin/rooms', b),
  update: (id: string, b: unknown) => patch<Room>(`/admin/rooms/${id}`, b),
};
export const ratesApi = {
  list: () => get<RoomRate[]>('/admin/room-rates'),
  create: (b: unknown) => post<RoomRate>('/admin/room-rates', b),
};
export const taxApi = {
  list: () => get<TaxSettings[]>('/admin/tax-settings'),
  create: (b: unknown) => post<TaxSettings>('/admin/tax-settings', b),
};
export const restaurantApi = {
  get: () => get<Restaurant | null>('/admin/restaurant'),
  patch: (b: unknown) => patch<Restaurant>('/admin/restaurant', b),
  categories: () => get<MenuCategory[]>('/admin/menu-categories'),
  createCategory: (b: unknown) => post<MenuCategory>('/admin/menu-categories', b),
  updateCategory: (id: string, b: unknown) => patch<MenuCategory>(`/admin/menu-categories/${id}`, b),
  items: (category_id?: string) => get<MenuItem[]>(category_id ? `/admin/menu-items?category_id=${category_id}&page=1&page_size=100` : '/admin/menu-items?page=1&page_size=100'),
  createItem: (b: unknown) => post<MenuItem>('/admin/menu-items', b),
  updateItem: (id: string, b: unknown) => patch<MenuItem>(`/admin/menu-items/${id}`, b),
};
export const cabApi = {
  list: () => get<CabProvider[]>('/admin/cab-providers'),
  create: (b: unknown) => post<CabProvider>('/admin/cab-providers', b),
  update: (id: string, b: unknown) => patch<CabProvider>(`/admin/cab-providers/${id}`, b),
};
