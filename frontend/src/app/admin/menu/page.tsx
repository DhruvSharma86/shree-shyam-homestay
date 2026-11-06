'use client';
import Image from 'next/image';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { menuCategorySchema, menuItemSchema } from '@/schemas';
import { restaurantApi } from '@/services/hotel';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

export default function MenuPage() {
  const qc = useQueryClient();
  const cats = useQuery({ queryKey: ['menu-cats'], queryFn: () => restaurantApi.categories() });
  const items = useQuery({ queryKey: ['menu-items'], queryFn: () => restaurantApi.items() });
  const [err, setErr] = useState('');
  const catForm = useForm({ resolver: zodResolver(menuCategorySchema) });
  const itemForm = useForm({ resolver: zodResolver(menuItemSchema) });

  const createCat = useMutation({
    mutationFn: (v: unknown) => restaurantApi.createCategory(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['menu-cats'] }); catForm.reset({ name: '', display_order: 0 } as never); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const createItem = useMutation({
    mutationFn: (v: unknown) => restaurantApi.createItem(v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['menu-items'] }); itemForm.reset({ name: '', price: '', category_id: '', is_vegetarian: true, display_order: 0 } as never); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const toggleItem = useMutation({
    mutationFn: (v: { id: string; is_available: boolean }) => restaurantApi.updateItem(v.id, { is_available: v.is_available }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['menu-items'] }),
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  if (cats.isLoading || items.isLoading) return <Spinner />;
  const catName = (id: string) => (cats.data ?? []).find((c) => c.id === id)?.name ?? id.slice(0, 8);

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Menu</h1>
      <p className="text-sm text-stone-500">Photographs are referenced by URL (no file upload API exists yet — do not expect uploads).</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-medium">Add category</h2>
          <form onSubmit={catForm.handleSubmit((v) => createCat.mutate(v))} className="mt-3 space-y-3">
            <Field label="Name" error={catForm.formState.errors.name?.message}><Input {...catForm.register('name')} /></Field>
            <Field label="Description"><Input {...catForm.register('description')} /></Field>
            <Field label="Display order"><Input type="number" {...catForm.register('display_order')} /></Field>
            <Button type="submit" disabled={createCat.isPending}>Add</Button>
          </form>
          <h2 className="mt-6 font-medium">Categories</h2>
          {(cats.data ?? []).length === 0 ? <Empty title="No categories yet" /> : (cats.data ?? []).map((c) => <p key={c.id} className="text-sm">{c.name} — {c.is_active ? 'Active' : 'Inactive'} (order {c.display_order})</p>)}
        </Card>
        <Card>
          <h2 className="font-medium">Add item</h2>
          <form onSubmit={itemForm.handleSubmit((v) => createItem.mutate(v))} className="mt-3 space-y-3">
            <Field label="Name" error={itemForm.formState.errors.name?.message}><Input {...itemForm.register('name')} /></Field>
            <Field label="Price (₹)" error={itemForm.formState.errors.price?.message}><Input inputMode="decimal" {...itemForm.register('price')} /></Field>
            <Field label="Category" error={itemForm.formState.errors.category_id?.message}>
              <select {...itemForm.register('category_id')} className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm">
                <option value="">Select…</option>
                {(cats.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Image URL (https)" error={itemForm.formState.errors.image_url?.message}><Input type="url" {...itemForm.register('image_url')} /></Field>
            <Field label="Display order"><Input type="number" {...itemForm.register('display_order')} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" {...itemForm.register('is_vegetarian')} /> Vegetarian</label>
            <Button type="submit" disabled={createItem.isPending}>Add item</Button>
          </form>
        </Card>
      </div>
      <div className="mt-4">
        {(items.data ?? []).length === 0 ? <Empty title="No items yet" /> : null}
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {(items.data ?? []).map((it) => (
            <Card key={it.id}>
              {it.image_url ? <Image src={it.image_url} alt={it.name} width={400} height={160} unoptimized className="mb-2 h-32 w-full rounded-md object-cover" /> : null}
              <p className="font-medium">{it.name}</p>
              <p className="text-sm text-stone-500">{catName(it.category_id)} · ₹{it.price} · {it.is_vegetarian ? 'Veg' : 'Non-veg'}</p>
              <Button className="mt-2" onClick={() => toggleItem.mutate({ id: it.id, is_available: !it.is_available })}>{it.is_available ? 'Mark unavailable' : 'Mark available'}</Button>
            </Card>
          ))}
        </div>
      </div>
      {err ? <Err message={err} /> : null}
    </div>
  );
}
