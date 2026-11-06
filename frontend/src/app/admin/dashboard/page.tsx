'use client';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { roomsApi, roomTypesApi, ratesApi, restaurantApi, cabApi, hotelApi } from '@/services/hotel';
import { Card, Empty, Spinner } from '@/components/ui/primitives';

export default function DashboardPage() {
  const rooms = useQuery({ queryKey: ['rooms'], queryFn: () => roomsApi.list() });
  const types = useQuery({ queryKey: ['room-types'], queryFn: () => roomTypesApi.list() });
  const rates = useQuery({ queryKey: ['rates'], queryFn: () => ratesApi.list() });
  const rest = useQuery({ queryKey: ['restaurant'], queryFn: () => restaurantApi.get() });
  const cabs = useQuery({ queryKey: ['cabs'], queryFn: () => cabApi.list() });
  const hotel = useQuery({ queryKey: ['hotel'], queryFn: () => hotelApi.get() });

  const anyLoading = [rooms, types, rates, rest, cabs, hotel].some((q) => q.isLoading);
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
      <p className="text-sm text-stone-500">Configuration summary. No booking, revenue or occupancy figures are shown until those systems exist.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map(([label, value, href]) => (
          <Link key={label} href={href}><Card><p className="text-sm text-stone-500">{label}</p><p className="text-2xl font-semibold">{value}</p></Card></Link>
        ))}
      </div>
      {roomList.length === 0 ? <div className="mt-4"><Empty title="No rooms configured yet" hint="Add rooms under Rooms — numbers are assigned by you, never invented by the system." /></div> : null}
    </div>
  );
}
