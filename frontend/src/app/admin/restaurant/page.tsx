'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { restaurantSchema } from '@/schemas';
import { restaurantApi } from '@/services/hotel';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Err, Field, Input, Spinner } from '@/components/ui/primitives';

export default function RestaurantPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['restaurant'], queryFn: () => restaurantApi.get() });
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');
  const { register, handleSubmit, reset } = useForm({ resolver: zodResolver(restaurantSchema) });

  useEffect(() => { if (q.data) reset(q.data as never); }, [q.data, reset]);

  const save = useMutation({
    mutationFn: (v: unknown) => restaurantApi.patch(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['restaurant'] }); setOk('Saved.'); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  if (q.isLoading) return <Spinner />;
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Restaurant</h1>
      <Card className="mt-4 max-w-xl">
        <form onSubmit={handleSubmit((v) => save.mutate(v))} className="space-y-3">
          <Field label="Name"><Input {...register('name')} /></Field>
          <Field label="Description"><Input {...register('description')} /></Field>
          <Field label="Contact number"><Input {...register('contact_number')} /></Field>
          <Field label="Opening hours"><Input {...register('opening_hours')} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" {...register('is_active')} /> Active</label>
          <Button type="submit" disabled={save.isPending}>Save</Button>
          {ok ? <p role="status" className="text-sm text-green-700">{ok}</p> : null}
        </form>
      </Card>
      <p className="mt-3 text-sm text-stone-500">Menu categories and items live under <a className="underline" href="/admin/menu">Menu</a>.</p>
      {err ? <Err message={err} /> : null}
    </div>
  );
}
