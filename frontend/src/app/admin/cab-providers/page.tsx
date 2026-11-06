'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { cabSchema } from '@/schemas';
import { cabApi } from '@/services/hotel';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

export default function CabPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['cabs'], queryFn: () => cabApi.list() });
  const [err, setErr] = useState('');
  const { register, handleSubmit, reset, formState: { errors } } = useForm({ resolver: zodResolver(cabSchema) });

  const create = useMutation({
    mutationFn: (v: unknown) => cabApi.create(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cabs'] }); reset({ company_name: '', contact_number: '', display_order: 0 } as never); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const toggle = useMutation({
    mutationFn: (v: { id: string; is_active: boolean }) => cabApi.update(v.id, { is_active: v.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cabs'] }),
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  if (q.isLoading) return <Spinner />;
  const rows = q.data ?? [];

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Cab providers</h1>
      <p className="text-sm text-stone-500">Shown on the guest portal later. No booking integration here.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-medium">Add provider</h2>
          <form onSubmit={handleSubmit((v) => create.mutate(v))} className="mt-3 space-y-3">
            <Field label="Company name" error={errors.company_name?.message}><Input {...register('company_name')} /></Field>
            <Field label="Contact number" error={errors.contact_number?.message}><Input {...register('contact_number')} /></Field>
            <Field label="Website URL"><Input type="url" {...register('website_url')} /></Field>
            <Field label="Description"><Input {...register('description')} /></Field>
            <Field label="Service description"><Input {...register('service_description')} /></Field>
            <Field label="Display order"><Input type="number" {...register('display_order')} /></Field>
            <Button type="submit" disabled={create.isPending}>Add</Button>
          </form>
        </Card>
        <div className="space-y-2">
          {rows.length === 0 ? <Empty title="No cab providers yet" /> : null}
          {rows.map((c) => (
            <Card key={c.id} className="flex items-center justify-between">
              <div><p className="font-medium">{c.company_name}</p><p className="text-sm text-stone-500">{c.contact_number} · {c.website_url ?? 'No website'} · {c.is_active ? 'Active' : 'Inactive'}</p></div>
              <Button onClick={() => toggle.mutate({ id: c.id, is_active: !c.is_active })}>{c.is_active ? 'Deactivate' : 'Activate'}</Button>
            </Card>
          ))}
        </div>
      </div>
      {err ? <Err message={err} /> : null}
    </div>
  );
}
