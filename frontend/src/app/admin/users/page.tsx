'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { userCreateSchema } from '@/schemas';
import { createUser, listUsers, resetPassword, updateUser } from '@/services/auth';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

export default function UsersPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['users'], queryFn: () => listUsers() });
  const [err, setErr] = useState('');
  const [resetPw, setResetPw] = useState<Record<string, string>>({});
  const { register, handleSubmit, reset, formState: { errors } } = useForm({ resolver: zodResolver(userCreateSchema) });

  const create = useMutation({
    mutationFn: (v: unknown) => createUser(v as Record<string, unknown>),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); reset(); },
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const toggle = useMutation({
    mutationFn: (v: { id: string; is_active: boolean }) => updateUser(v.id, { is_active: v.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
    onError: (e) => setErr(apiErrorMessage(e)),
  });
  const doReset = useMutation({
    mutationFn: (v: { id: string; pw: string }) => resetPassword(v.id, v.pw),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
    onError: (e) => setErr(apiErrorMessage(e)),
  });

  if (q.isLoading) return <Spinner />;
  const rows = q.data ?? [];

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
      <p className="text-sm text-stone-500">No public registration — accounts are only created here. Password hashes are never shown.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-medium">Create account</h2>
          <form onSubmit={handleSubmit((v) => create.mutate(v))} className="mt-3 space-y-3">
            <Field label="Username" error={errors.username?.message}><Input {...register('username')} /></Field>
            <Field label="Full name" error={errors.full_name?.message}><Input {...register('full_name')} /></Field>
            <Field label="Email (optional)" error={errors.email?.message}><Input type="email" {...register('email')} /></Field>
            <Field label="Password (≥10)" error={errors.password?.message}><Input type="password" {...register('password')} /></Field>
            <Field label="Role" error={errors.role?.message}>
              <select {...register('role')} className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm"><option value="RECEPTIONIST">Receptionist</option><option value="ADMIN">Admin</option></select>
            </Field>
            <Button type="submit" disabled={create.isPending}>Create</Button>
          </form>
        </Card>
        <div className="space-y-2">
          {rows.length === 0 ? <Empty title="No users" /> : null}
          {rows.map((u) => (
            <Card key={u.id} className="space-y-2">
              <p className="font-medium">{u.full_name} <span className="text-sm text-stone-500">@{u.username} · {u.role} · {u.is_active ? 'Active' : 'Inactive'}</span></p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => toggle.mutate({ id: u.id, is_active: !u.is_active })}>{u.is_active ? 'Deactivate' : 'Activate'}</Button>
                <input placeholder="New password (≥10)" type="password" className="rounded-md border border-stone-300 px-2 py-1 text-sm" value={resetPw[u.id] ?? ''} onChange={(e) => setResetPw({ ...resetPw, [u.id]: e.target.value })} />
                <Button disabled={!resetPw[u.id]} onClick={() => doReset.mutate({ id: u.id, pw: resetPw[u.id] ?? '' })}>Reset password</Button>
              </div>
            </Card>
          ))}
        </div>
      </div>
      {err ? <Err message={err} /> : null}
    </div>
  );
}
