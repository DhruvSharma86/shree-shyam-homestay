'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { roomSchema } from '@/schemas';
import { roomsApi, roomTypesApi } from '@/services/hotel';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

export default function RoomsPage() {
  const qc = useQueryClient();
  const rooms = useQuery({ queryKey: ['rooms'], queryFn: () => roomsApi.list() });
  const types = useQuery({ queryKey: ['room-types'], queryFn: () => roomTypesApi.list() });
  const [err, setErr] = useState('');
  const [filter, setFilter] = useState('');
  const { register, handleSubmit, reset, formState: { errors } } = useForm({ resolver: zodResolver(roomSchema) });

  const create = useMutation({
    mutationFn: (v: unknown) => roomsApi.create(v),
    onMutate: () => setErr(''),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rooms'] }); reset(); setErr(''); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const patch = useMutation({
    mutationFn: (v: { id: string; b: unknown }) => roomsApi.update(v.id, v.b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rooms'] }),
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  if (rooms.isLoading || types.isLoading) return <Spinner />;
  const typeName = (id: string) => (types.data ?? []).find((t) => t.id === id)?.name ?? id.slice(0, 8);
  const rows = (rooms.data ?? []).filter((r) => {
    if (!filter) return true;
    if (filter === 'INACTIVE') return r.is_active === false;
    return r.is_active === true && r.operational_status === filter;
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Rooms</h1>
      <p className="text-sm text-stone-500">Operational status only — booking occupancy lives in the booking system (later phase).</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-medium">Add room</h2>
          <form onSubmit={handleSubmit((v) => create.mutate(v))} className="mt-3 space-y-3">
            <Field label="Room number" error={errors.room_number?.message}><Input {...register('room_number')} /></Field>
            <Field label="Room category" error={errors.room_type_id?.message}>
              <select {...register('room_type_id')} className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm">
                <option value="">Select…</option>
                {(types.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </Field>
            <Field label="Floor (optional)" error={errors.floor?.message}><Input type="number" {...register('floor')} /></Field>
            <Field label="Maximum occupancy" error={errors.maximum_occupancy?.message}><Input type="number" {...register('maximum_occupancy')} /></Field>
            <Field label="Description"><Input {...register('description')} /></Field>
            <Button type="submit" disabled={create.isPending}>Add room</Button>
          </form>
        </Card>
        <div>
          <label className="mb-2 block text-sm">Filter by status
            <select value={filter} onChange={(e) => setFilter(e.target.value)} className="ml-2 rounded-md border border-stone-300 px-2 py-1 text-sm">
              <option value="">All</option><option value="AVAILABLE">Available</option><option value="MAINTENANCE">Maintenance</option><option value="INACTIVE">Inactive</option>
            </select>
          </label>
          {rows.length === 0 ? <Empty title="No rooms yet" hint="Add the six rooms here — numbers are assigned by you." /> : null}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-stone-500"><th className="py-2 pr-2">Number</th><th className="py-2 pr-2">Category</th><th className="py-2 pr-2">Status</th><th className="py-2 pr-2">Active</th><th /></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t">
                    <td className="py-2 pr-2 font-medium">{r.room_number}</td>
                    <td className="py-2 pr-2">{typeName(r.room_type_id)}</td>
                    <td className="py-2 pr-2"><span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs">{r.operational_status}</span></td>
                    <td className="py-2 pr-2">{r.is_active ? 'Yes' : 'No'}</td>
                    <td className="py-2 flex gap-2">
                      <Button onClick={() => patch.mutate({ id: r.id, b: { operational_status: r.operational_status === 'MAINTENANCE' ? 'AVAILABLE' : 'MAINTENANCE' } })}>Toggle maintenance</Button>
                      <Button onClick={() => patch.mutate({ id: r.id, b: { is_active: !r.is_active } })}>{r.is_active ? 'Deactivate' : 'Activate'}</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      {err ? <Err message={err} /> : null}
    </div>
  );
}
