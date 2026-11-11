'use client';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { roomsApi, roomTypesApi, ratesApi, restaurantApi, cabApi, hotelApi } from '@/services/hotel';
import { reportsApi } from '@/services/reports';
import { Card, Empty, Spinner } from '@/components/ui/primitives';

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(v);
}

export default function DashboardPage() {
  const rooms = useQuery({ queryKey: ['rooms'], queryFn: () => roomsApi.list() });
  const types = useQuery({ queryKey: ['room-types'], queryFn: () => roomTypesApi.list() });
  const rates = useQuery({ queryKey: ['rates'], queryFn: () => ratesApi.list() });
  const rest = useQuery({ queryKey: ['restaurant'], queryFn: () => restaurantApi.get() });
  const cabs = useQuery({ queryKey: ['cabs'], queryFn: () => cabApi.list() });
  const hotel = useQuery({ queryKey: ['hotel'], queryFn: () => hotelApi.get() });

  const summary = useQuery({
    queryKey: ['reports', 'financial-summary'],
    queryFn: () => reportsApi.financialSummary(undefined, undefined),
    retry: false,
  });

  const occupancy = useQuery({
    queryKey: ['reports', 'occupancy'],
    queryFn: () => reportsApi.occupancy(undefined, undefined),
    retry: false,
  });

  const bookings = useQuery({
    queryKey: ['reports', 'bookings-summary'],
    queryFn: () => reportsApi.bookingsSummary(undefined, undefined),
    retry: false,
  });

  const anyLoading = [rooms, types, rates, rest, cabs, hotel, summary, occupancy, bookings].some((q) => q.isLoading);
  if (anyLoading) return <Spinner />;

  const roomList = rooms.data ?? [];
  const activeRooms = roomList.filter((r) => r.is_active && r.operational_status === 'AVAILABLE').length;

  const cards: [string, string, string][] = [
    ['Configured rooms', String(roomList.length), '/admin/rooms'],
    ['Active rooms', String(activeRooms), '/admin/rooms'],
    ['Room categories', String((types.data ?? []).filter((t) => t.is_active).length), '/admin/room-types'],
    ['Configured rates', String((rates.data ?? []).filter((r) => r.is_active).length), '/admin/room-rates'],
    ['Restaurant', rest.data ? (rest.data.is_active ? 'Active' : 'Inactive') : 'Not configured', '/admin/restaurant'],
    ['Cab providers', String((cabs.data ?? []).filter((c) => c.is_active).length), '/admin/cab-providers'],
  ];

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Welcome{hotel.data ? `, ${hotel.data.hotel_name}` : ''}</h1>
      <p className="text-sm text-stone-500">Configuration summary. Financial and occupancy figures below are for all time.</p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map(([label, value, href]) => (
          <Link key={label} href={href}><Card><p className="text-sm text-stone-500">{label}</p><p className="text-2xl font-semibold">{value}</p></Card></Link>
        ))}
        <Card>
          <p className="text-sm text-stone-500">Gross charges</p>
          <p className="text-2xl font-semibold">{money(summary.data?.gross_charges ?? null)}</p>
        </Card>
        <Card>
          <p className="text-sm text-stone-500">Net payments</p>
          <p className="text-2xl font-semibold">{money(summary.data?.net_payments ?? null)}</p>
        </Card>
        <Card>
          <p className="text-sm text-stone-500">Outstanding balance</p>
          <p className={`text-2xl font-semibold ${(summary.data?.outstanding ?? 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>{money(summary.data?.outstanding ?? null)}</p>
        </Card>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <p className="text-sm text-stone-500">Current occupancy rate</p>
          <p className="text-2xl font-semibold">{occupancy.data?.occupancy_rate != null ? `${occupancy.data.occupancy_rate}%` : '—'}</p>
        </Card>
        <Card>
          <p className="text-sm text-stone-500">Total bookings</p>
          <p className="text-2xl font-semibold">{bookings.data?.total ?? 0}</p>
        </Card>
        <Card>
          <p className="text-sm text-stone-500">Pending balances</p>
          <p className="text-2xl font-semibold">{money(summary.data?.outstanding ?? null)}</p>
        </Card>
      </div>

      {roomList.length === 0 ? <div className="mt-4"><Empty title="No rooms configured yet" hint="Add rooms under Rooms — numbers are assigned by you, never invented by the system." /></div> : null}
    </div>
  );
}
