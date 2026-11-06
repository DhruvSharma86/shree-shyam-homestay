'use client';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { hotelSchema } from '@/schemas';
import { hotelApi } from '@/services/hotel';
import { apiErrorMessage } from '@/lib/api';
import { Button, Card, Field, Input, Spinner } from '@/components/ui/primitives';

export default function HotelPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['hotel'], queryFn: () => hotelApi.get() });
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');
  const { register, handleSubmit, reset, formState: { errors } } = useForm({ resolver: zodResolver(hotelSchema) });

  useEffect(() => {
    if (q.data) reset({ ...q.data, wifi_password: '' } as never);
  }, [q.data, reset]);

  if (q.isLoading) return <Spinner />;
  if (q.isError) return <p role="alert">{apiErrorMessage(q.error)}</p>;

  async function onSubmit(values: Record<string, unknown>) {
    try {
      const clean = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== '' && v !== undefined));
      await hotelApi.patch(clean);
      setOk('Hotel information saved.');
      qc.invalidateQueries({ queryKey: ['hotel'] });
    } catch (e) { setErr(apiErrorMessage(e)); }
  }

  const f = (name: string, label: string, type = 'text') => (
    <Field key={name} label={label} error={(errors as Record<string, { message?: string }>)[name]?.message}>
      <Input type={type} {...register(name as never)} />
    </Field>
  );

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Hotel information</h1>
      <Card className="mt-4 max-w-2xl">
        <form onSubmit={handleSubmit(onSubmit)} className="grid gap-3 sm:grid-cols-2">
          {f('hotel_name', 'Hotel name')}
          {f('city', 'City')}
          {f('state', 'State')}
          {f('pincode', 'PIN code')}
          {f('contact_number', 'Contact number')}
          {f('alternate_contact_number', 'Alternate contact')}
          {f('email', 'Email', 'email')}
          {f('website_url', 'Website URL', 'url')}
          <div className="sm:col-span-2">{f('address', 'Address')}</div>
          <div className="sm:col-span-2">{f('description', 'Description')}</div>
          {f('google_maps_url', 'Google Maps URL', 'url')}
          {f('logo_url', 'Logo URL', 'url')}
          {f('check_in_time', 'Check-in time')}
          {f('check_out_time', 'Check-out time')}
          {f('wifi_ssid', 'Wi-Fi SSID')}
          {f('wifi_password', 'Wi-Fi password (write-only)', 'password')}
          {err ? <p role="alert" className="text-sm text-red-600 sm:col-span-2">{err}</p> : null}
          {ok ? <p role="status" className="text-sm text-green-700 sm:col-span-2">{ok}</p> : null}
          <Button type="submit" className="sm:col-span-2">Save</Button>
        </form>
      </Card>
    </div>
  );
}
