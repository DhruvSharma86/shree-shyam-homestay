'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { localInfoSchema, tourPackageSchema } from '@/schemas';
import { tourismApi } from '@/services/tourism';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

export default function TourismPage() {
  const qc = useQueryClient();
  const [err, setErr] = useState('');
  const packages = useQuery({ queryKey: ['tour-packages'], queryFn: () => tourismApi.packages() });
  const info = useQuery({ queryKey: ['local-info'], queryFn: () => tourismApi.localInfo() });
  const pkgForm = useForm({ resolver: zodResolver(tourPackageSchema) });
  const infoForm = useForm({ resolver: zodResolver(localInfoSchema) });

  const createPackage = useMutation({
    mutationFn: (v: unknown) => tourismApi.createPackage(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tour-packages'] }); pkgForm.reset({} as never); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const togglePackage = useMutation({
    mutationFn: (v: { id: string; is_active: boolean }) => tourismApi.updatePackage(v.id, { is_active: v.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tour-packages'] }),
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const createInfo = useMutation({
    mutationFn: (v: unknown) => tourismApi.createLocalInfo(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['local-info'] }); infoForm.reset({} as never); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const toggleInfo = useMutation({
    mutationFn: (v: { id: string; is_active: boolean }) => tourismApi.updateLocalInfo(v.id, { is_active: v.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['local-info'] }),
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Tourism &amp; local information</h1>
      <p className="text-sm text-stone-500">Shown on the guest portal. Content only — no booking or payments here.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-medium">Add tour package</h2>
          <form onSubmit={pkgForm.handleSubmit((v) => createPackage.mutate(v))} className="mt-3 space-y-3">
            <Field label="Name" error={pkgForm.formState.errors.name?.message}><Input {...pkgForm.register('name')} /></Field>
            <Field label="Description"><Input {...pkgForm.register('description')} /></Field>
            <Field label="Duration"><Input {...pkgForm.register('duration')} /></Field>
            <Field label="Price (optional)"><Input {...pkgForm.register('price')} /></Field>
            <Field label="Image URL"><Input type="url" {...pkgForm.register('image_url')} /></Field>
            <Field label="Contact number"><Input {...pkgForm.register('contact_number')} /></Field>
            <Field label="Display order"><Input type="number" {...pkgForm.register('display_order')} defaultValue={0} /></Field>
            <Button type="submit" disabled={createPackage.isPending}>Add</Button>
          </form>
        </Card>
        <Card>
          <h2 className="font-medium">Add local information</h2>
          <form onSubmit={infoForm.handleSubmit((v) => createInfo.mutate(v))} className="mt-3 space-y-3">
            <Field label="Title" error={infoForm.formState.errors.title?.message}><Input {...infoForm.register('title')} /></Field>
            <Field label="Description"><Input {...infoForm.register('description')} /></Field>
            <Field label="Location"><Input {...infoForm.register('location')} /></Field>
            <Field label="Contact number"><Input {...infoForm.register('contact_number')} /></Field>
            <Field label="Image URL"><Input type="url" {...infoForm.register('image_url')} /></Field>
            <Field label="Display order"><Input type="number" {...infoForm.register('display_order')} defaultValue={0} /></Field>
            <Button type="submit" disabled={createInfo.isPending}>Add</Button>
          </form>
        </Card>
      </div>
      <h2 className="mt-6 font-medium">Tour packages</h2>
      {packages.isLoading ? <Spinner /> : (
        <div className="mt-2 space-y-2">
          {(packages.data ?? []).length === 0 ? <Empty title="No tour packages yet" /> : null}
          {(packages.data ?? []).map((p) => (
            <Card key={p.id} className="flex items-center justify-between">
              <div><p className="font-medium">{p.name}</p><p className="text-sm text-stone-500">{p.duration ?? ''} {p.price ? `· INR ${p.price}` : ''} · {p.is_active ? 'Active' : 'Inactive'}</p></div>
              <Button onClick={() => togglePackage.mutate({ id: p.id, is_active: !p.is_active })}>{p.is_active ? 'Deactivate' : 'Activate'}</Button>
            </Card>
          ))}
        </div>
      )}
      <h2 className="mt-6 font-medium">Local information</h2>
      {info.isLoading ? <Spinner /> : (
        <div className="mt-2 space-y-2">
          {(info.data ?? []).length === 0 ? <Empty title="No local information yet" /> : null}
          {(info.data ?? []).map((i) => (
            <Card key={i.id} className="flex items-center justify-between">
              <div><p className="font-medium">{i.title}</p><p className="text-sm text-stone-500">{i.location ?? ''} · {i.is_active ? 'Active' : 'Inactive'}</p></div>
              <Button onClick={() => toggleInfo.mutate({ id: i.id, is_active: !i.is_active })}>{i.is_active ? 'Deactivate' : 'Activate'}</Button>
            </Card>
          ))}
        </div>
      )}
      {err ? <Err message={err} /> : null}
    </div>
  );
}
