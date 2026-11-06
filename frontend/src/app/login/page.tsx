'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { loginSchema } from '@/schemas';
import { login } from '@/services/auth';
import { apiErrorMessage } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { Button, Card, Field, Input } from '@/components/ui/primitives';

export default function LoginPage() {
  const router = useRouter();
  const setMe = useAuthStore((s) => s.setMe);
  const [err, setErr] = useState('');
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({ resolver: zodResolver(loginSchema) });

  async function onSubmit(values: { username: string; password: string }) {
    try {
      const me = await login(values.username, values.password);
      setMe(me);
      router.replace('/admin/dashboard');
    } catch (e) { setErr(apiErrorMessage(e)); }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md items-center p-6">
      <Card className="w-full">
        <h1 className="text-xl font-semibold tracking-tight">Shree Shyam Home Stay</h1>
        <p className="text-sm text-stone-500">Staff sign-in</p>
        <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-3" noValidate>
          <Field label="Username" error={errors.username?.message}>
            <Input {...register('username')} autoComplete="username" />
          </Field>
          <Field label="Password" error={errors.password?.message}>
            <Input {...register('password')} type="password" autoComplete="current-password" />
          </Field>
          {err ? <p className="text-sm text-red-600" role="alert">{err}</p> : null}
          <Button type="submit" disabled={isSubmitting} className="w-full">{isSubmitting ? 'Signing in…' : 'Sign in'}</Button>
        </form>
      </Card>
    </main>
  );
}
