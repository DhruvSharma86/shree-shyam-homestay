'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { taxSchema } from '@/schemas';
import { taxApi } from '@/services/hotel';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

export default function TaxPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['tax'], queryFn: () => taxApi.list() });
  const [err, setErr] = useState('');
  const { register, handleSubmit, reset, formState: { errors } } = useForm({ resolver: zodResolver(taxSchema) });

  const create = useMutation({
    mutationFn: (v: unknown) => taxApi.create(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tax'] }); reset(); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  if (q.isLoading) return <Spinner />;
  const rows = q.data ?? [];

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Tax settings</h1>
      <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">Default is NONE (no tax). Do not assume GST registration — configure only what the property is actually registered for and what the law requires.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-medium">Add settings version</h2>
          <form onSubmit={handleSubmit((v) => create.mutate(v))} className="mt-3 space-y-3">
            <Field label="Registration status"><Input {...register('registration_status')} /></Field>
            <Field label="Tax type" error={errors.tax_type?.message}><Input {...register('tax_type')} /></Field>
            <Field label="Rate (required unless NONE)" error={errors.tax_rate?.message}><Input inputMode="decimal" {...register('tax_rate')} /></Field>
            <Field label="Pricing mode" error={errors.pricing_mode?.message}>
              <select {...register('pricing_mode')} className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm"><option value="EXCLUSIVE">Exclusive</option><option value="INCLUSIVE">Inclusive</option></select>
            </Field>
            <Field label="Valid from" error={errors.valid_from?.message}><Input type="date" {...register('valid_from')} /></Field>
            <Field label="Valid until (optional)"><Input type="date" {...register('valid_until')} /></Field>
            <Button type="submit" disabled={create.isPending}>Save version</Button>
          </form>
        </Card>
        <div>
          {rows.length === 0 ? <Empty title="No tax configured (NONE)" hint="History will appear here once versions are added." /> : null}
          {rows.map((r) => (
            <Card key={r.id} className="mb-2"><p className="font-medium">{r.tax_type} {r.tax_rate ? `${r.tax_rate}%` : ''}</p>
            <p className="text-sm text-stone-500">{r.pricing_mode} · {r.valid_from} → {r.valid_until ?? 'open'}</p></Card>
          ))}
        </div>
      </div>
      {err ? <Err message={err} /> : null}
    </div>
  );
}
