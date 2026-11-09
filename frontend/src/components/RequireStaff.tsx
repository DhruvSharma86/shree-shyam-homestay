'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore, isAdmin } from '@/stores/auth';
import { fetchMe } from '@/services/auth';
import type { MeResponse } from '@/types';

/** Shared session resolution for route guards (fetchMe exactly once). */
export function useSession(): { me: MeResponse | null; loading: boolean } {
  const { me, loading, setMe, setLoading } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    if (me) { setLoading(false); return; }
    setLoading(true);
    fetchMe().then((m) => { if (!cancelled) setMe(m); })
      .catch(() => { if (!cancelled) router.replace('/login'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me]);

  return { me, loading };
}

/** Guard for authenticated staff (ADMIN or RECEPTIONIST). */
export function RequireStaff({ children }: { children: React.ReactNode }) {
  const { me, loading } = useSession();
  if (loading || !me) return <p className="p-6 text-sm text-stone-500" role="status">Loading…</p>;
  return <>{children}</>;
}

/**
 * Guard for genuinely ADMIN-only sections.
 */
export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { me, loading } = useSession();
  if (loading || !me) return <p className="p-6 text-sm text-stone-500" role="status">Loading…</p>;
  if (!isAdmin(me.permissions, me.user.role)) return (
    <div className="p-6"><h1 className="text-lg font-semibold">Access restricted</h1>
    <p className="text-sm text-stone-500 mt-1">Admin role required. Receptionist dashboard is a later milestone.</p></div>
  );
  return <>{children}</>;
}
