import { create } from 'zustand';
import type { MeResponse } from '@/types';

interface AuthState {
  me: MeResponse | null;
  loading: boolean;
  setMe: (m: MeResponse | null) => void;
  setLoading: (b: boolean) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  me: null,
  loading: false,
  setMe: (me) => set({ me, loading: false }),
  setLoading: (loading) => set({ loading }),
  clear: () => set({ me: null, loading: false }),
}));

export function isAdmin(perms: string[] | undefined, role?: string): boolean {
  return role === 'ADMIN' || (perms ?? []).includes('users.manage');
}
