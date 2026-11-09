'use client';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { downloadReceipt, guestPortalApi } from '@/services/guestPortal';
import { Button, Card, Empty, Err, Spinner } from '@/components/ui/primitives';

function telHref(phone: string): string {
  return `tel:${phone.replace(/[^+\d]/g, '')}`;
}

export function GuestPortalView({ token }: { token: string }) {
  const overview = useQuery({ queryKey: ['guest-overview', token], queryFn: () => guestPortalApi.overview(token) });
  const menu = useQuery({ queryKey: ['guest-menu', token], queryFn: () => guestPortalApi.menu(token) });
  const cab = useQuery({ queryKey: ['guest-cab', token], queryFn: () => guestPortalApi.cab(token) });
  const wifi = useQuery({ queryKey: ['guest-wifi', token], queryFn: () => guestPortalApi.wifi(token) });
  const tourism = useQuery({ queryKey: ['guest-tourism', token], queryFn: () => guestPortalApi.tourism(token) });
  const receipt = useQuery({ queryKey: ['guest-receipt', token], queryFn: () => guestPortalApi.receipt(token), retry: false });

  const [copiedWifi, setCopiedWifi] = useState(false);
  const [wifiError, setWifiError] = useState('');
  const [receiptError, setReceiptError] = useState('');

  const loading = overview.isLoading;

  async function onDownload() {
    setReceiptError('');
    try {
      const blob = await downloadReceipt(token);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${receipt.data?.receipt_ref ?? 'receipt'}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      setReceiptError('The receipt could not be downloaded right now. Please try again or ask reception.');
    }
  }

  async function onCopyWifi(password: string) {
    setCopiedWifi(false);
    setWifiError('');
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(password);
      } else {
        // Insecure-context fallback (older mobile browsers).
        const ta = document.createElement('textarea');
        ta.value = password;
        ta.setAttribute('readonly', '');
        ta.style.position = 'absolute';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopiedWifi(true);
    } catch {
      setWifiError('Copying did not work on this device. Please type the password manually.');
    }
  }

  if (loading) return <div className="mx-auto max-w-3xl p-4"><Spinner /></div>;
  if (overview.isError) {
    return (
      <div className="mx-auto max-w-3xl p-4">
        <Card>
          <div role="alert">
            <h1 className="text-xl font-semibold">This link is no longer valid</h1>
            <p className="mt-2 text-sm text-stone-600">
              Your guest link may have expired or been replaced. Please call reception if your stay is still open.
            </p>
          </div>
        </Card>
      </div>
    );
  }
  const data = overview.data;
  if (!data) return <div className="mx-auto max-w-3xl p-4"><Spinner /></div>;

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4">
      <header className="min-w-0">
        <h1 className="break-words text-2xl font-semibold tracking-tight sm:text-3xl">Welcome to {data.hotel_name}</h1>
        <p className="break-words text-sm text-stone-500">Booking {data.booking_ref} · Room {data.room_number} ({data.room_type})</p>
      </header>

      <section aria-labelledby="stay-heading">
        <Card>
          <h2 id="stay-heading" className="font-medium">Your stay</h2>
          <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
            <div className="min-w-0"><dt className="text-stone-500">Check-in</dt><dd className="break-words">{data.check_in_date}</dd></div>
            <div className="min-w-0"><dt className="text-stone-500">Check-out</dt><dd className="break-words">{data.check_out_date}</dd></div>
            <div className="min-w-0"><dt className="text-stone-500">Nights</dt><dd className="break-words">{data.nights}</dd></div>
            <div className="min-w-0"><dt className="text-stone-500">Status</dt><dd className="break-words">{data.status}</dd></div>
          </dl>
          {data.expires_at ? (
            <p className="mt-2 break-words text-xs text-stone-500">Link available until {data.expires_at.replace('T', ' ').slice(0, 16)} (24h after checkout)</p>
          ) : null}
          {data.contact.contact_number || data.contact.email ? (
            <p className="mt-2 break-words text-sm text-stone-600">
              Reception:{' '}
              {data.contact.contact_number ? (
                <a className="underline underline-offset-2" href={telHref(data.contact.contact_number)} aria-label={`Call reception at ${data.contact.contact_number}`}>
                  {data.contact.contact_number}
                </a>
              ) : null}
              {data.contact.contact_number && data.contact.email ? ' · ' : null}
              {data.contact.email ? (
                <a className="break-all underline underline-offset-2" href={`mailto:${data.contact.email}`} aria-label={`Email reception at ${data.contact.email}`}>
                  {data.contact.email}
                </a>
              ) : null}
            </p>
          ) : null}
        </Card>
      </section>

      <section aria-labelledby="menu-heading">
        <Card>
          <h2 id="menu-heading" className="font-medium">Restaurant menu</h2>
          {menu.isLoading ? <Spinner /> : menu.isError ? <Err message="Menu is unavailable right now." /> : (
            (menu.data?.categories.length ?? 0) === 0 ? <Empty title="No menu published yet" /> : (
            <div className="mt-2 space-y-4">
              {menu.data?.categories.map((cat) => (
                <div key={cat.category} className="min-w-0">
                  <h3 className="break-words font-medium">{cat.category}</h3>
                  <ul className="mt-1 space-y-2">
                    {cat.items.map((item) => (
                      <li key={`${cat.category}-${item.name}`} className="flex items-start gap-3">
                        {item.image_url ? (
                          // eslint-disable-next-line @next/next/no-img-element -- external menu photos can't use next/image without remote config
                          <img src={item.image_url} alt={item.name} className="h-12 w-12 shrink-0 rounded object-cover" loading="lazy" referrerPolicy="no-referrer" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                        ) : null}
                        <div className="min-w-0 flex-1">
                          <p className="break-words text-sm">{item.name} {item.is_vegetarian ? <span className="text-xs text-green-700">(Veg)</span> : null}</p>
                          {item.description ? <p className="break-words text-xs text-stone-500">{item.description}</p> : null}
                          <p className="break-words text-sm text-stone-700">INR {item.price}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>)
          )}
        </Card>
      </section>

      <section aria-labelledby="cab-heading">
        <Card>
          <h2 id="cab-heading" className="font-medium">Cabs</h2>
          {cab.isLoading ? <Spinner /> : cab.isError ? <Err message="Cab information is unavailable right now." /> : (
            (cab.data?.providers.length ?? 0) === 0 ? <Empty title="No cab providers listed yet" /> : (
            <div className="mt-2 space-y-4">
              {cab.data?.providers.map((p) => (
                <div key={p.company_name} className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0 flex-1">
                    <p className="break-words font-medium">{p.company_name}</p>
                    <p className="break-words text-sm text-stone-600">{p.contact_number}</p>
                    {p.description ? <p className="break-words text-sm text-stone-500">{p.description}</p> : null}
                    {p.service_description ? <p className="break-words text-xs text-stone-500">{p.service_description}</p> : null}
                  </div>
                  <a
                    href={telHref(p.contact_number)}
                    aria-label={`Call ${p.company_name} at ${p.contact_number}`}
                    className="inline-flex min-h-11 shrink-0 items-center justify-center gap-1 rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-900 focus-visible:ring-offset-2"
                  >
                    Call
                  </a>
                </div>
              ))}
            </div>)
          )}
        </Card>
      </section>

      <section aria-labelledby="tourism-heading">
        <Card>
          <h2 id="tourism-heading" className="font-medium">Tourism &amp; local information</h2>
          {tourism.isLoading ? <Spinner /> : tourism.isError ? <Err message="Local information is unavailable right now." /> : (
            <>
              {(tourism.data?.packages.length ?? 0) === 0 && (tourism.data?.local_info.length ?? 0) === 0 ? (
                <Empty title="No local guide yet" hint="Ask reception for suggestions." />
              ) : null}
              <div className="mt-2 space-y-4">
                {tourism.data?.packages.map((p) => (
                  <div key={p.name} className="min-w-0">
                    <p className="break-words font-medium">{p.name}</p>
                    {p.duration ? <p className="break-words text-xs text-stone-500">{p.duration}</p> : null}
                    {p.description ? <p className="break-words text-sm text-stone-600">{p.description}</p> : null}
                    {p.price ? <p className="break-words text-sm text-stone-700">INR {p.price}</p> : null}
                    {p.contact_number ? (
                      <p className="break-words text-sm text-stone-600">
                        Enquiries:{' '}
                        <a className="underline underline-offset-2" href={telHref(p.contact_number)} aria-label={`Call ${p.name} at ${p.contact_number}`}>
                          {p.contact_number}
                        </a>
                      </p>
                    ) : null}
                  </div>
                ))}
                {tourism.data?.local_info.map((i) => (
                  <div key={i.title} className="min-w-0">
                    <p className="break-words font-medium">{i.title}</p>
                    {i.location ? <p className="break-words text-xs text-stone-500">{i.location}</p> : null}
                    {i.description ? <p className="break-words text-sm text-stone-600">{i.description}</p> : null}
                    {i.contact_number ? (
                      <p className="break-words text-sm text-stone-600">
                        Contact:{' '}
                        <a className="underline underline-offset-2" href={telHref(i.contact_number)} aria-label={`Call ${i.title} at ${i.contact_number}`}>
                          {i.contact_number}
                        </a>
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </section>

      <section aria-labelledby="wifi-heading">
        <Card>
          <h2 id="wifi-heading" className="font-medium">Wi-Fi</h2>
          {wifi.isLoading ? <Spinner /> : wifi.isError ? <Err message="Wi-Fi information is unavailable." /> : (
            !wifi.data?.ssid ? <Empty title="No Wi-Fi details configured" /> : (
            <div className="mt-2 space-y-2">
              <p className="break-all text-sm"><b>Network:</b> {wifi.data.ssid}</p>
              <p className="break-all text-sm"><b>Password:</b> {wifi.data.password}</p>
              <Button
                type="button"
                onClick={() => void onCopyWifi(wifi.data?.password ?? '')}
                aria-label={`Copy Wi-Fi password${copiedWifi ? ' (copied)' : ''}`}
              >
                {copiedWifi ? 'Copied' : 'Copy password'}
              </Button>
              {copiedWifi ? <p className="text-sm text-stone-600" role="status">Wi-Fi password copied.</p> : null}
              {wifiError ? <p className="text-sm text-red-700" role="alert">{wifiError}</p> : null}
            </div>)
          )}
        </Card>
      </section>

      <section aria-labelledby="receipt-heading">
        <Card>
          <h2 id="receipt-heading" className="font-medium">Receipt</h2>
          {receipt.isLoading ? <Spinner /> : receipt.isError ? (
            <Empty title="Receipt not available yet" hint="Your final receipt appears here after checkout." />
          ) : (
            <div className="mt-2 space-y-2">
              <p className="break-words text-sm">Receipt {receipt.data?.receipt_ref}</p>
              <Button
                type="button"
                onClick={() => void onDownload()}
                aria-label={`Download final receipt PDF ${receipt.data?.receipt_ref}`}
              >
                Download PDF
              </Button>
              {receiptError ? <p className="text-sm text-red-700" role="alert">{receiptError}</p> : null}
            </div>
          )}
        </Card>
      </section>
    </main>
  );
}
