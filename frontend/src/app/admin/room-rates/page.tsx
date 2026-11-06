'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { rateSchema } from '@/schemas';
import { ratesApi, roomTypesApi } from '@/services/hotel';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

export default function RatesPage() {
  const qc = useQueryClient();
  const rates = useQuery({ queryKey: ['rates'], queryFn: () => ratesApi.list() });
  const types = useQuery({ queryKey: ['room-types'], queryFn: () => roomTypesApi.list() });
  const [err, setErr] = useState('');
  const { register, handleSubmit, reset, formState: { errors } } = useForm({ resolver: zodResolver(rateSchema) });

  const create = useMutation({
    mutationFn: (v: unknown) => ratesApi.create(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rates'] }); reset(); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  if (rates.isLoading || types.isLoading) return <Spinner />;
  const typeName = (id: string) => (types.data ?? []).find((t) => t.id === id)?.name ?? id.slice(0, 8);
  const rows = rates.data ?? [];

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Room rates</h1>
      <p className="text-sm text-stone-500">Rates are append-only — a price change creates a new version and never overwrites history. Amounts in INR (₹).</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-medium">Add rate version</h2>
          <form onSubmit={handleSubmit((v) => create.mutate(v))} className="mt-3 space-y-3">
            <Field label="Room category" error={errors.room_type_id?.message}>
              <select {...register('room_type_id')} className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm">
                <option value="">Select…</option>
                {(types.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </Field>
            <Field label="Nightly price (₹)" error={errors.nightly_rate?.message}><Input inputMode="decimal" {...register('nightly_rate')} /></Field>
            <Field label="Valid from" error={errors.valid_from?.message}><Input type="date" {...register('valid_from')} /></Field>
            <Field label="Valid until (optional)"><Input type="date" {...register('valid_until')} /></Field>
            <Button type="submit" disabled={create.isPending}>Add rate</Button>
          </form>
        </Card>
        <div>
          {rows.length === 0 ? <Empty title="No rates yet" hint="Add the first nightly rate for a category." /> : null}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-stone-500"><th className="py-2 pr-2">Category</th><th className="py-2 pr-2">Nightly (₹)</th><th className="py-2 pr-2">From</th><th className="py-2 pr-2">Until</th><th className="py-2 pr-2">Active</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t">
                    <td className="py-2 pr-2">{typeName(r.room_type_id)}</td>
                    <td className="py-2 pr-2">₹{r.nightly_rate}</td>
                    <td className="py-2 pr-2">{r.valid_from}</td>
                    <td className="py-2 pr-2">{r.valid_until ?? '—'}</td>
                    <td className="py-2 pr-2">{r.is_active ? 'Yes' : 'No'}</td>
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
