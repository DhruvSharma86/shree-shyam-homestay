'use client';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bookingsApi } from '@/services/tourism';
import { apiErrorMessage } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PREFIX = process.env.NEXT_PUBLIC_API_V1 ?? '/api/v1';

export default function BookingsPage() {
  const qc = useQueryClient();
  const { me } = useAuthStore();
  // Portal administration (rotate/revoke) is ADMIN-only in the backend;
  // hide the controls for receptionists entirely (backend still enforces
  // the denial independently).
  const canAdminPortal = (me?.permissions ?? []).includes('portal.tokens.manage');
  const [selected, setSelected] = useState<string | null>(null);
  const [err, setErr] = useState('');
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [payment, setPayment] = useState({ amount: '', mode: 'CASH' });

  const list = useQuery({ queryKey: ['bookings'], queryFn: () => bookingsApi.list() });
  const detail = useQuery({ queryKey: ['booking', selected], queryFn: () => bookingsApi.get(selected as string), enabled: !!selected });

  const recordPayment = useMutation({
    mutationFn: () => bookingsApi.recordCheckInPayment(selected as string, { amount: payment.amount, mode: payment.mode, payment_stage: 'CHECK_IN' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['booking', selected] }); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const checkIn = useMutation({
    mutationFn: () => bookingsApi.checkIn(selected as string),
    onSuccess: (result) => {
      // Raw token is shown once for staff relay; never persisted.
      setLinkToken(result.portal_access_token);
      qc.invalidateQueries({ queryKey: ['booking', selected] });
    },
    onError: (e) => {
      setLinkToken(null);
      setErr(apiErrorMessage(e));
    },
  });
  const rotate = useMutation({
    mutationFn: () => bookingsApi.rotatePortal(selected as string),
    onSuccess: (result) => setLinkToken(result.portal_access_token),
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const revoke = useMutation({
    mutationFn: () => bookingsApi.revokePortal(selected as string),
    onSuccess: () => {
      setLinkToken(null);
      qc.invalidateQueries({ queryKey: ['booking', selected] });
    },
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  function clearLink() {
    setLinkToken(null);
    setCopied(false);
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Bookings</h1>
      <p className="text-sm text-stone-500">Check-in issues the guest&apos;s one-time portal link. Rotate/revoke is ADMIN-only.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          {list.isLoading ? <Spinner /> : null}
          {(list.data?.items ?? []).length === 0 ? <Empty title="No bookings yet" /> : null}
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
          {!selected ? <Empty title="Select a booking" /> : detail.isLoading ? <Spinner /> : !detail.data ? (
            <Empty title="Booking not found" />
          ) : (
            <div className="space-y-3">
              <h2 className="font-medium">{detail.data.booking_ref} · {detail.data.status}</h2>
              <p className="text-sm text-stone-600">
                {detail.data.check_in_date} → {detail.data.check_out_date} ({detail.data.nights} nights)
              </p>
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
                  <p className="mt-1 break-all text-sm">
                    {`${BASE}${PREFIX}/guest/${linkToken}`}
                  </p>
                  <div className="mt-2 flex gap-2">
                    <Button
                      type="button"
                      onClick={() => { void navigator.clipboard?.writeText(`${BASE}${PREFIX}/guest/${linkToken}`); setCopied(true); }}
                    >
                      {copied ? 'Copied' : 'Copy link'}
                    </Button>
                    <Button type="button" onClick={clearLink}>Dismiss</Button>
                  </div>
                  <p className="mt-2 text-xs text-stone-500">
                    Rotation revokes the previous link. If the link is lost, rotate it (ADMIN-only).
                  </p>
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
