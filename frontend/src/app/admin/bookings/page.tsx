'use client';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { bookingsApi } from '@/services/tourism';
import { guestsApi } from '@/services/guests';
import { apiErrorMessage, mutationErrorMessage } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { Button, Card, Empty, Err, Field, Input, RetryButton, Spinner } from '@/components/ui/primitives';

// (no backend base constants needed; guest links use the frontend origin)

const bookingSchema = z.object({
  check_in_date: z.string().min(1, 'Check-in date is required'),
  check_out_date: z.string().min(1, 'Check-out date is required'),
  number_of_guests: z.coerce.number().int().min(1).max(20),
  source: z.enum(['PHONE', 'WALK_IN']),
  notes: z.string().optional(),
});

const guestLink = (token: string) => `${typeof window !== 'undefined' ? window.location.origin : ''}/guest/${token}`;

export default function BookingsPage() {
  const qc = useQueryClient();
  const { me } = useAuthStore();
  const canAdminPortal = (me?.permissions ?? []).includes('portal.tokens.manage');
  const [selected, setSelected] = useState<string | null>(null);
  const [err, setErr] = useState('');
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [payment, setPayment] = useState({ amount: '', mode: 'CASH' });

  // Create-booking state
  const [showCreate, setShowCreate] = useState(false);
  const [guestQuery, setGuestQuery] = useState('');
  const [guestSearch, setGuestSearch] = useState('');
  const [selectedGuest, setSelectedGuest] = useState<{ id: string; full_name: string } | null>(null);
  const [availRooms, setAvailRooms] = useState<{ room_id: string; available: boolean }[]>([]);
  const [availLoading, setAvailLoading] = useState(false);
  const [availErr, setAvailErr] = useState('');
  const [selectedRoom, setSelectedRoom] = useState<string>('');
  const [roomMeta, setRoomMeta] = useState<Record<string, { room_number: string; room_type: string; max: number }>>({});

  const list = useQuery({ queryKey: ['bookings'], queryFn: () => bookingsApi.list() });
  const detail = useQuery({ queryKey: ['booking', selected], queryFn: () => bookingsApi.get(selected as string), enabled: !!selected });
  const guestsSearch = useQuery({ queryKey: ['guests-search', guestSearch], queryFn: () => guestsApi.list(guestSearch, 1, 20), enabled: guestSearch.length > 0 });

  const { register, handleSubmit, reset: resetForm, formState: { errors } } = useForm({ resolver: zodResolver(bookingSchema), defaultValues: { source: 'PHONE', number_of_guests: 1 } });

  const createBooking = useMutation({
    mutationFn: (v: unknown) => bookingsApi.create({ ...(v as Record<string, unknown>), guest_id: selectedGuest!.id, room_id: selectedRoom }),
    retry: false,
    onSuccess: (result: { id: string }) => {
      qc.invalidateQueries({ queryKey: ['bookings'] });
      setErr('');
      setShowCreate(false);
      setSelected(result.id);
      resetForm();
      setSelectedGuest(null);
      setSelectedRoom('');
      setAvailRooms([]);
    },
    onError: (e) => setErr(mutationErrorMessage(e)),
  });

  const recordPayment = useMutation({
    mutationFn: () => bookingsApi.recordCheckInPayment(selected as string, { amount: payment.amount, mode: payment.mode, payment_stage: 'CHECK_IN' }),
    retry: false,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['booking', selected] }); },
    onError: (e) => setErr(mutationErrorMessage(e)),
  });
  const checkIn = useMutation({
    mutationFn: () => bookingsApi.checkIn(selected as string),
    retry: false,
    onSuccess: (result) => {
      setLinkToken(result.portal_access_token);
      qc.invalidateQueries({ queryKey: ['booking', selected] });
    },
    onError: (e) => { setLinkToken(null); setErr(mutationErrorMessage(e)); },
  });
  const rotate = useMutation({
    mutationFn: () => bookingsApi.rotatePortal(selected as string),
    retry: false,
    onSuccess: (result) => setLinkToken(result.portal_access_token),
    onError: (e) => setErr(mutationErrorMessage(e)),
  });
  const revoke = useMutation({
    mutationFn: () => bookingsApi.revokePortal(selected as string),
    retry: false,
    onSuccess: () => { setLinkToken(null); qc.invalidateQueries({ queryKey: ['booking', selected] }); },
    onError: (e) => setErr(mutationErrorMessage(e)),
  });

  function clearLink() { setLinkToken(null); setCopied(false); }

  async function checkAvailability() {
    const ci = (document.getElementById('ci') as HTMLInputElement)?.value;
    const co = (document.getElementById('co') as HTMLInputElement)?.value;
    if (!ci || !co) { setAvailErr('Select both dates.'); return; }
    if (co <= ci) { setAvailErr('Check-out must be after check-in.'); return; }
    setAvailErr('');
    setAvailLoading(true);
    setAvailRooms([]);
    try {
      const res = await bookingsApi.availability(ci, co);
      setAvailRooms(res.map((r) => ({ room_id: r.room_id, available: r.available })));
    } catch (e) {
      setAvailErr(apiErrorMessage(e));
    } finally {
      setAvailLoading(false);
    }
  }

  // fetch room meta for display (lazy, cached)
  // We'll fetch rooms list once when creating
  useQuery({ queryKey: ['rooms-meta'], queryFn: async () => {
    const r = await (await import('@/services/hotel')).roomsApi.list();
    // also fetch room types
    const types = await (await import('@/services/hotel')).roomTypesApi.list();
    const tmap = new Map(types.map((t: { id: string; name: string }) => [t.id, t.name]));
    const meta: Record<string, { room_number: string; room_type: string; max: number }> = {};
    for (const room of r) meta[room.id] = { room_number: room.room_number, room_type: tmap.get(room.room_type_id) ?? room.room_type_id, max: room.maximum_occupancy };
    setRoomMeta(meta);
    return r;
  }, enabled: showCreate });

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Bookings</h1>
        <Button type="button" onClick={() => setShowCreate((s) => !s)}>{showCreate ? 'Cancel' : 'Create booking'}</Button>
      </div>
      <p className="text-sm text-stone-500">Check-in issues the guest&apos;s one-time portal link. Rotate/revoke is ADMIN-only.</p>

      {showCreate ? (
        <Card className="mt-4 space-y-4">
          <h2 className="font-medium">Create booking</h2>
          {/* Guest selection */}
          <div className="space-y-2">
            <label className="block text-sm font-medium">Guest</label>
            <div className="flex gap-2">
              <Input placeholder="Search by name/phone…" value={guestQuery} onChange={(e) => setGuestQuery(e.target.value)} />
              <Button type="button" onClick={() => setGuestSearch(guestQuery)}>Search</Button>
            </div>
            {selectedGuest ? (
              <p className="text-sm text-stone-600">Selected: <b>{selectedGuest.full_name}</b> <button type="button" className="text-xs underline" onClick={() => setSelectedGuest(null)}>change</button></p>
            ) : null}
            {guestSearch && guestsSearch.isLoading ? <Spinner /> : null}
            {guestSearch && !guestsSearch.isLoading && (guestsSearch.data?.items ?? []).length === 0 ? <Empty title="No guests found" hint="Register the guest first." /> : null}
            {(guestsSearch.data?.items ?? []).map((g: { id: string; full_name: string; phone: string }) => (
              <button key={g.id} type="button" onClick={() => { setSelectedGuest({ id: g.id, full_name: g.full_name }); setGuestSearch(''); }} className="block w-full rounded-md border border-stone-200 px-3 py-2 text-left text-sm hover:bg-stone-50">
                {g.full_name} · {g.phone}
              </button>
            ))}
          </div>

          {/* Dates */}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Check-in date"><Input id="ci" type="date" {...register('check_in_date')} /></Field>
            <Field label="Check-out date"><Input id="co" type="date" {...register('check_out_date')} /></Field>
          </div>
          {errors.check_in_date ? <Err message={errors.check_in_date.message as string} /> : null}
          {errors.check_out_date ? <Err message={errors.check_out_date.message as string} /> : null}

          <div className="flex gap-2">
            <Button type="button" onClick={checkAvailability} disabled={availLoading}>{availLoading ? 'Checking…' : 'Check availability'}</Button>
          </div>
          {availErr ? <Err message={availErr} /> : null}

          {/* Available rooms */}
          {availRooms.length > 0 ? (
            <div className="space-y-2">
              <p className="text-sm font-medium">Available rooms</p>
              {availRooms.filter((r) => r.available).map((r) => {
                const m = roomMeta[r.room_id];
                return (
                  <label key={r.room_id} className="flex items-center gap-2 rounded-md border border-stone-200 px-3 py-2 text-sm">
                    <input type="radio" name="room" value={r.room_id} checked={selectedRoom === r.room_id} onChange={() => setSelectedRoom(r.room_id)} />
                    <span>Room {m?.room_number ?? r.room_id.slice(0, 6)} ({m?.room_type}) — max {m?.max} guests</span>
                  </label>
                );
              })}
              {availRooms.filter((r) => r.available).length === 0 ? <Empty title="No rooms available for these dates" /> : null}
            </div>
          ) : null}

          {/* Guests + source + notes */}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Number of guests" error={errors.number_of_guests?.message}><Input type="number" min={1} max={20} {...register('number_of_guests')} /></Field>
            <Field label="Source">
              <select {...register('source')} className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm">
                <option value="PHONE">PHONE</option>
                <option value="WALK_IN">WALK_IN</option>
              </select>
            </Field>
          </div>
          <Field label="Notes"><Input {...register('notes')} /></Field>

          {selectedRoom && roomMeta[selectedRoom] ? (
            <p className="text-xs text-stone-500">Selected room capacity: {roomMeta[selectedRoom].max} guests.</p>
          ) : null}

          <div className="flex gap-2">
            <Button type="submit" disabled={createBooking.isPending || !selectedGuest || !selectedRoom} onClick={handleSubmit((v) => createBooking.mutate(v))}>
              {createBooking.isPending ? 'Creating…' : 'Create booking'}
            </Button>
          </div>
          {err ? <Err message={err} /> : null}
        </Card>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          {list.isLoading ? <Spinner /> : null}
          {list.isError ? (
            <div className="space-y-2">
              <Err message={apiErrorMessage(list.error)} />
              <RetryButton onRetry={() => void list.refetch()} label="Retry loading bookings" />
            </div>
          ) : null}
          {!list.isError && (list.data?.items ?? []).length === 0 ? <Empty title="No bookings yet" /> : null}
          {(list.data?.items ?? []).map((b) => (
            <Card key={b.id} className="flex items-center justify-between">
              <div>
                <p className="font-medium">{b.booking_ref}</p>
                <p className="text-sm text-stone-500">{b.status} · {b.check_in_date} → {b.check_out_date}</p>
              </div>
              <Button onClick={() => { setSelected(b.id); clearLink(); }}>Open</Button>
            </Card>
          ))}
        </div>
        <Card>
          {!selected ? <Empty title="Select a booking" /> : detail.isLoading ? <Spinner /> : detail.isError ? (
            <div className="space-y-2">
              <Err message={apiErrorMessage(detail.error)} />
              <RetryButton onRetry={() => void detail.refetch()} label="Retry loading booking details" />
            </div>
          ) : !detail.data ? (
            <Empty title="Booking not found" />
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="font-medium">{detail.data.booking_ref} · {detail.data.status}</h2>
                <a href={`/admin/bookings/${detail.data.id}/folio`} className="text-sm text-stone-600 hover:text-stone-900 underline">View Folio</a>
              </div>
              <p className="text-sm text-stone-600">
                {detail.data.check_in_date} → {detail.data.check_out_date} ({detail.data.nights} nights) · {detail.data.number_of_guests} guest(s)
              </p>
              <p className="text-sm text-stone-500">Source: {detail.data.source}</p>
              {detail.data.status === 'CONFIRMED' ? (
                <>
                  <div className="flex gap-2">
                    <Field label="One-night payment (CHECK_IN)">
                      <div className="flex gap-2">
                        <Input placeholder="2500.00" value={payment.amount} onChange={(e) => setPayment({ ...payment, amount: e.target.value })} />
                        <select value={payment.mode} onChange={(e) => setPayment({ ...payment, mode: e.target.value })} className="rounded-md border border-stone-300 px-2">
                          <option value="CASH">CASH</option>
                          <option value="UPI">UPI</option>
                          <option value="CARD_POS">CARD_POS</option>
                        </select>
                      </div>
                    </Field>
                  </div>
                  <Button type="button" onClick={() => recordPayment.mutate()} disabled={recordPayment.isPending}>
                    Record one-night payment
                  </Button>
                  <Button type="button" onClick={() => checkIn.mutate()} disabled={checkIn.isPending}>
                    Check in &amp; issue guest link
                  </Button>
                </>
              ) : null}
              {linkToken ? (
                <div className="rounded-md border border-amber-300 bg-amber-50 p-3" role="status">
                  <p className="text-sm font-medium">Share this link with the guest (shown once — it will not appear again):</p>
                  <p className="mt-1 break-all text-sm">{guestLink(linkToken)}</p>
                  <div className="mt-2 flex gap-2">
                    <Button type="button" onClick={() => { void navigator.clipboard?.writeText(guestLink(linkToken)); setCopied(true); }}>
                      {copied ? 'Copied' : 'Copy link'}
                    </Button>
                    <Button type="button" onClick={clearLink}>Dismiss</Button>
                  </div>
                </div>
              ) : null}
              {!canAdminPortal && detail.data.status === 'CHECKED_IN' ? (
                <p className="mt-2 text-xs text-stone-500">
                  The guest link is shown only once at check-in and cannot be retrieved again.
                  If the guest cannot find it, ask an ADMIN to rotate the link (rotation revokes the previous one).
                </p>
              ) : null}
              {canAdminPortal && detail.data.status === 'CHECKED_IN' ? (
                <div className="flex flex-wrap gap-2">
                  <Button type="button" onClick={() => rotate.mutate()} disabled={rotate.isPending}>Rotate link (ADMIN)</Button>
                  <Button type="button" onClick={() => revoke.mutate()} disabled={revoke.isPending}>Revoke link (ADMIN)</Button>
                </div>
              ) : null}
            </div>
          )}
        </Card>
      </div>
      {err ? <Err message={err} /> : null}
    </div>
  );
}
