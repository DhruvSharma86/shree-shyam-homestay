'use client';
import { useQuery } from '@tanstack/react-query';
import { downloadReceipt, guestPortalApi } from '@/services/guestPortal';
import { Button, Card, Empty, Err, Spinner } from '@/components/ui/primitives';

export function GuestPortalView({ token }: { token: string }) {
  const overview = useQuery({ queryKey: ['guest-overview', token], queryFn: () => guestPortalApi.overview(token) });
  const menu = useQuery({ queryKey: ['guest-menu', token], queryFn: () => guestPortalApi.menu(token) });
  const cab = useQuery({ queryKey: ['guest-cab', token], queryFn: () => guestPortalApi.cab(token) });
  const wifi = useQuery({ queryKey: ['guest-wifi', token], queryFn: () => guestPortalApi.wifi(token) });
  const tourism = useQuery({ queryKey: ['guest-tourism', token], queryFn: () => guestPortalApi.tourism(token) });
  const receipt = useQuery({ queryKey: ['guest-receipt', token], queryFn: () => guestPortalApi.receipt(token), retry: false });

  const loading = overview.isLoading;

  async function onDownload() {
    const blob = await downloadReceipt(token);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${receipt.data?.receipt_ref ?? 'receipt'}.pdf`;
    a.click();
    window.URL.revokeObjectURL(url);
  }

  if (loading) return <div className="mx-auto max-w-3xl p-4"><Spinner /></div>;
  if (overview.isError) {
    return (
      <div className="mx-auto max-w-3xl p-4">
        <Card>
          <h1 className="text-xl font-semibold">This link is no longer valid</h1>
          <p className="mt-2 text-sm text-stone-600">
            Your guest link may have expired or been replaced. Please call reception if your stay is still open.
          </p>
        </Card>
      </div>
    );
  }
  const data = overview.data;
  if (!data) return <div className="mx-auto max-w-3xl p-4"><Spinner /></div>;

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome to {data.hotel_name}</h1>
        <p className="text-sm text-stone-500">Booking {data.booking_ref} · Room {data.room_number} ({data.room_type})</p>
      </header>

      <Card>
        <h2 className="font-medium">Your stay</h2>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
          <div><dt className="text-stone-500">Check-in</dt><dd>{data.check_in_date}</dd></div>
          <div><dt className="text-stone-500">Check-out</dt><dd>{data.check_out_date}</dd></div>
          <div><dt className="text-stone-500">Nights</dt><dd>{data.nights}</dd></div>
          <div><dt className="text-stone-500">Status</dt><dd>{data.status}</dd></div>
        </dl>
        {data.expires_at ? (
          <p className="mt-2 text-xs text-stone-500">Link available until {data.expires_at.replace('T', ' ').slice(0, 16)} (24h after checkout)</p>
        ) : null}
        {data.contact.contact_number || data.contact.email ? (
          <p className="mt-2 text-sm text-stone-600">
            Reception: {[data.contact.contact_number, data.contact.email].filter(Boolean).join(' · ')}
          </p>
        ) : null}
      </Card>

      <Card>
        <h2 className="font-medium">Restaurant menu</h2>
        {menu.isLoading ? <Spinner /> : menu.isError ? <Err message="Menu is unavailable right now." /> : (
          (menu.data?.categories.length ?? 0) === 0 ? <Empty title="No menu published yet" /> : (
          <div className="mt-2 space-y-4">
            {menu.data?.categories.map((cat) => (
              <div key={cat.category}>
                <h3 className="font-medium">{cat.category}</h3>
                <ul className="mt-1 space-y-2">
                  {cat.items.map((item) => (
                    <li key={`${cat.category}-${item.name}`} className="flex items-start gap-3">
                      {item.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element -- external menu photos can't use next/image without remote config
                        <img src={item.image_url} alt="" className="h-12 w-12 rounded object-cover" loading="lazy" referrerPolicy="no-referrer" />
                      ) : null}
                      <div>
                        <p className="text-sm">{item.name} {item.is_vegetarian ? <span className="text-xs text-green-700">(Veg)</span> : null}</p>
                        {item.description ? <p className="text-xs text-stone-500">{item.description}</p> : null}
                        <p className="text-sm text-stone-700">INR {item.price}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>)
        )}
      </Card>

      <Card>
        <h2 className="font-medium">Cabs</h2>
        {cab.isLoading ? <Spinner /> : cab.isError ? <Err message="Cab information is unavailable right now." /> : (
          (cab.data?.providers.length ?? 0) === 0 ? <Empty title="No cab providers listed yet" /> : (
          <div className="mt-2 space-y-3">
            {cab.data?.providers.map((p) => (
              <div key={p.company_name} className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium">{p.company_name}</p>
                  {p.description ? <p className="text-sm text-stone-500">{p.description}</p> : null}
                  {p.service_description ? <p className="text-xs text-stone-500">{p.service_description}</p> : null}
                </div>
                <Button onClick={() => { window.location.href = `tel:${p.contact_number.replace(/[^+\d]/g, '')}`; }}>
                  Call
                </Button>
              </div>
            ))}
          </div>)
        )}
      </Card>

      <Card>
        <h2 className="font-medium">Tourism &amp; local information</h2>
        {tourism.isLoading ? <Spinner /> : tourism.isError ? <Err message="Local information is unavailable right now." /> : (
          <>
            {(tourism.data?.packages.length ?? 0) === 0 && (tourism.data?.local_info.length ?? 0) === 0 ? (
              <Empty title="No local guide yet" hint="Ask reception for suggestions." />
            ) : null}
            <div className="mt-2 space-y-3">
              {tourism.data?.packages.map((p) => (
                <div key={p.name}>
                  <p className="font-medium">{p.name}</p>
                  {p.duration ? <p className="text-xs text-stone-500">{p.duration}</p> : null}
                  {p.description ? <p className="text-sm text-stone-600">{p.description}</p> : null}
                  {p.price ? <p className="text-sm text-stone-700">INR {p.price}</p> : null}
                  {p.contact_number ? <p className="text-sm text-stone-600">Enquiries: {p.contact_number}</p> : null}
                </div>
              ))}
              {tourism.data?.local_info.map((i) => (
                <div key={i.title}>
                  <p className="font-medium">{i.title}</p>
                  {i.location ? <p className="text-xs text-stone-500">{i.location}</p> : null}
                  {i.description ? <p className="text-sm text-stone-600">{i.description}</p> : null}
                  {i.contact_number ? <p className="text-sm text-stone-600">Contact: {i.contact_number}</p> : null}
                </div>
              ))}
            </div>
          </>
        )}
      </Card>

      <Card>
        <h2 className="font-medium">Wi-Fi</h2>
        {wifi.isLoading ? <Spinner /> : wifi.isError ? <Err message="Wi-Fi information is unavailable." /> : (
          !wifi.data?.ssid ? <Empty title="No Wi-Fi details configured" /> : (
          <div className="mt-2 space-y-2">
            <p className="text-sm"><b>Network:</b> {wifi.data.ssid}</p>
            <p className="text-sm"><b>Password:</b> {wifi.data.password}</p>
            <Button
              type="button"
              onClick={() => void navigator.clipboard?.writeText(wifi.data?.password ?? '')}
            >
              Copy password
            </Button>
          </div>)
        )}
      </Card>

      <Card>
        <h2 className="font-medium">Receipt</h2>
        {receipt.isLoading ? <Spinner /> : receipt.isError ? (
          <Empty title="Receipt not available yet" hint="Your final receipt appears here after checkout." />
        ) : (
          <div className="mt-2 space-y-2">
            <p className="text-sm">Receipt {receipt.data?.receipt_ref}</p>
            <Button type="button" onClick={() => void onDownload()}>Download PDF</Button>
          </div>
        )}
      </Card>
    </main>
  );
}
