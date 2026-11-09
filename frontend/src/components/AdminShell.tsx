'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/auth';
import { logout } from '@/services/auth';

const NAV = [
  ['Dashboard', '/admin/dashboard'],
  ['Bookings', '/admin/bookings'],
  ['Hotel', '/admin/hotel'],
  ['Room types', '/admin/room-types'],
  ['Rooms', '/admin/rooms'],
  ['Room rates', '/admin/room-rates'],
  ['Tax settings', '/admin/tax-settings'],
  ['Restaurant', '/admin/restaurant'],
  ['Menu', '/admin/menu'],
  ['Cab providers', '/admin/cab-providers'],
  ['Tourism', '/admin/tourism'],
  ['Users', '/admin/users'],
  ['Audit logs', '/admin/audit-logs'],
] as const;

export function AdminShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { me, clear } = useAuthStore();
  const router = useRouter();

  async function onLogout() {
    try { await logout(); } catch { /* still clear */ }
    clear();
    router.replace('/login');
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="w-full shrink-0 border-b border-stone-200 bg-white p-4 md:w-56 md:border-b-0 md:border-r">
        <p className="font-semibold tracking-tight">Shree Shyam Home Stay</p>
        <p className="text-xs text-stone-500">Administration</p>
        <nav className="mt-4 space-y-1" aria-label="Admin">
          {NAV.map(([label, href]) => (
            <Link key={href} href={href} data-testid={`nav-${href.split('/').pop()}`}
              className={`block rounded-md px-2 py-1.5 text-sm ${path === href ? 'bg-stone-900 text-white' : 'hover:bg-stone-100'}`}>
              {label}
            </Link>
          ))}
        </nav>
        <div className="mt-6 border-t pt-4 text-sm">
          <p>{me?.user.full_name} <span className="text-stone-500">({me?.user.role})</span></p>
          <button onClick={onLogout} className="mt-2 text-sm text-red-700 hover:underline">Log out</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
    </div>
  );
}
