'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { roomTypeSchema } from '@/schemas';
import { roomTypesApi } from '@/services/hotel';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

export default function RoomTypesPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['room-types'], queryFn: () => roomTypesApi.list() });
  const [err, setErr] = useState('');
  const { register, handleSubmit, reset, formState: { errors } } = useForm({ resolver: zodResolver(roomTypeSchema) });

  const create = useMutation({
    mutationFn: (v: unknown) => roomTypesApi.create(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['room-types'] }); reset({ name: '', maximum_occupancy: 2, display_order: 0 } as never); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const toggle = useMutation({
    mutationFn: (v: { id: string; is_active: boolean }) => roomTypesApi.update(v.id, { is_active: v.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['room-types'] }),
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  if (q.isLoading) return <Spinner />;
  const rows = q.data ?? [];

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Room categories</h1>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-medium">Add category</h2>
          <form onSubmit={handleSubmit((v) => create.mutate(v))} className="mt-3 space-y-3">
            <Field label="Name" error={errors.name?.message}><Input {...register('name')} /></Field>
            <Field label="Description" error={errors.description?.message}><Input {...register('description')} /></Field>
            <Field label="Maximum occupancy" error={errors.maximum_occupancy?.message}><Input type="number" {...register('maximum_occupancy')} /></Field>
            <Field label="Amenities (comma-separated)"><Input {...register('amenities')} /></Field>
            <Field label="Display order"><Input type="number" {...register('display_order')} /></Field>
            <Button type="submit" disabled={create.isPending}>Add</Button>
          </form>
        </Card>
        <div className="space-y-2">
          {rows.length === 0 ? <Empty title="No categories yet" hint="Suggested: Normal, Deluxe, Super Deluxe — distribution is your choice." /> : null}
          {rows.map((r) => (
            <Card key={r.id} className="flex items-center justify-between">
              <div><p className="font-medium">{r.name}</p><p className="text-sm text-stone-500">Max {r.maximum_occupancy} · Order {r.display_order} · {r.is_active ? 'Active' : 'Inactive'}</p></div>
              <Button onClick={() => toggle.mutate({ id: r.id, is_active: !r.is_active })}>{r.is_active ? 'Deactivate' : 'Activate'}</Button>
            </Card>
          ))}
        </div>
      </div>
      {err ? <Err message={err} /> : null}
    </div>
  );
}
