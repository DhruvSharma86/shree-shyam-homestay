'use client';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { guestsApi } from '@/services/guests';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

const guestSchema = z.object({
  full_name: z.string().min(1, 'Name is required').max(160),
  phone: z.string().min(7, 'Phone is required').max(24),
  email: z.string().email('Invalid email').optional().or(z.literal('')),
  address: z.string().optional(),
  notes: z.string().optional(),
});

export default function GuestsPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');

  const list = useQuery({ queryKey: ['guests', search], queryFn: () => guestsApi.list(search, 1, 20) });

  const { register, handleSubmit, reset, formState: { errors } } = useForm({ resolver: zodResolver(guestSchema) });

  const create = useMutation({
    mutationFn: (v: unknown) => guestsApi.create(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['guests'] }); reset(); setOk('Guest registered.'); setErr(''); },
    onError: (e) => { setOk(''); setErr(apiErrorMessage(e)); },
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Guests</h1>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-medium">Register guest</h2>
          <form onSubmit={handleSubmit((v) => create.mutate(v))} className="mt-3 space-y-3">
            <Field label="Full name" error={errors.full_name?.message}><Input {...register('full_name')} /></Field>
            <Field label="Phone" error={errors.phone?.message}><Input {...register('phone')} /></Field>
            <Field label="Email" error={errors.email?.message}><Input type="email" {...register('email')} /></Field>
            <Field label="Address"><Input {...register('address')} /></Field>
            <Field label="Notes"><Input {...register('notes')} /></Field>
            <Button type="submit" disabled={create.isPending}>Register</Button>
            {ok ? <p role="status" className="text-sm text-green-700">{ok}</p> : null}
          </form>
        </Card>
        <div className="space-y-2">
          <div className="flex gap-2">
            <Input placeholder="Search guests…" value={q} onChange={(e) => setQ(e.target.value)} />
            <Button type="button" onClick={() => setSearch(q)}>Search</Button>
          </div>
          {list.isLoading ? <Spinner /> : null}
          {list.isError ? <Err message={apiErrorMessage(list.error)} /> : null}
          {!list.isLoading && !list.isError && (list.data?.items ?? []).length === 0 ? <Empty title="No guests found" /> : null}
          {(list.data?.items ?? []).map((g) => (
            <Card key={g.id} className="flex items-center justify-between">
              <div>
                <p className="font-medium">{g.full_name}</p>
                <p className="text-sm text-stone-500">{g.phone}{g.email ? ` · ${g.email}` : ''}</p>
              </div>
            </Card>
          ))}
        </div>
      </div>
      {err ? <Err message={err} /> : null}
    </div>
  );
}
