import { api } from '@/lib/api';
import type { MeResponse, UserResponse } from '@/types';

export async function login(username: string, password: string): Promise<MeResponse> {
  const r = await api.post<MeResponse>('/auth/login', { username, password });
  return r.data;
}
export async function logout(): Promise<void> { await api.post('/auth/logout'); }
export async function fetchMe(): Promise<MeResponse> {
  const r = await api.get<MeResponse>('/auth/me');
  return r.data;
}
export async function changePassword(current: string, next: string): Promise<void> {
  await api.post('/auth/change-password', { current_password: current, new_password: next });
}
export async function listUsers(): Promise<UserResponse[]> {
  const r = await api.get<UserResponse[]>('/users');
  return r.data;
}
export async function createUser(payload: Record<string, unknown>): Promise<UserResponse> {
  const r = await api.post<UserResponse>('/users', payload);
  return r.data;
}
export async function updateUser(id: string, payload: Record<string, unknown>): Promise<UserResponse> {
  const r = await api.patch<UserResponse>(`/users/${id}`, payload);
  return r.data;
}
export async function resetPassword(id: string, new_password: string): Promise<void> {
  await api.post(`/users/${id}/reset-password`, { new_password });
}
