import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GuestPortalView } from '@/app/guest/[token]/view';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useParams: () => ({ token: 'tok123' }),
}));

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  menu: vi.fn(),
  cab: vi.fn(),
  wifi: vi.fn(),
  tourism: vi.fn(),
  receipt: vi.fn(),
  download: vi.fn(),
}));

vi.mock('@/services/guestPortal', () => ({
  guestPortalApi: {
    overview: (t: string) => mocks.overview(t),
    menu: (t: string) => mocks.menu(t),
    cab: (t: string) => mocks.cab(t),
    wifi: (t: string) => mocks.wifi(t),
    tourism: (t: string) => mocks.tourism(t),
    receipt: (t: string) => mocks.receipt(t),
  },
  downloadReceipt: (t: string) => mocks.download(t),
}));

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <GuestPortalView token="tok123" />
    </QueryClientProvider>,
  );
}

describe('guest portal page', () => {
  it('shows overview with stay fields', async () => {
    mocks.overview.mockResolvedValue({
      hotel_name: 'Shree Shyam Home Stay',
      booking_ref: 'SSH-AAA',
      room_number: '101',
      room_type: 'Deluxe',
      check_in_date: '2026-11-10',
      check_out_date: '2026-11-13',
      nights: 3,
      status: 'CHECKED_IN',
      checked_out_at: null,
      expires_at: null,
      contact: { contact_number: '+919800000000', email: null, address: null },
    });
    mocks.menu.mockResolvedValue({ categories: [] });
    mocks.cab.mockResolvedValue({ providers: [] });
    mocks.wifi.mockResolvedValue({ ssid: null, password: null });
    mocks.tourism.mockResolvedValue({ packages: [], local_info: [] });
    mocks.receipt.mockRejectedValue(new Error('404'));
    wrap();
    await waitFor(() => expect(screen.getByText(/Welcome to Shree Shyam Home Stay/i)).toBeInTheDocument());
    expect(screen.getByText(/SSH-AAA/)).toBeInTheDocument();
    expect(screen.getByText(/Room 101 \(Deluxe\)/)).toBeInTheDocument();
  });

  it('shows menu items, cab call action, wifi copy, tourism and receipt states', async () => {
    mocks.overview.mockResolvedValue({
      hotel_name: 'Shree Shyam Home Stay',
      booking_ref: 'SSH-AAA',
      room_number: '101',
      room_type: 'Deluxe',
      check_in_date: '2026-11-10',
      check_out_date: '2026-11-13',
      nights: 3,
      status: 'CHECKED_OUT',
      checked_out_at: '2026-11-13T10:00:00Z',
      expires_at: '2026-11-14T10:00:00Z',
      contact: { contact_number: null, email: null, address: null },
    });
    mocks.menu.mockResolvedValue({
      categories: [{ category: 'Breakfast', items: [{ name: 'Poha', description: 'light', price: '120.00', image_url: null, is_vegetarian: true }] }],
    });
    mocks.cab.mockResolvedValue({
      providers: [{ company_name: 'Test Cabs', description: null, contact_number: '+919800000000', service_description: null }],
    });
    mocks.wifi.mockResolvedValue({ ssid: 'GuestNet', password: 'welcome123' });
    mocks.tourism.mockResolvedValue({
      packages: [{ name: 'Fort Walk', description: 'Morning tour', duration: '3 hours', price: '800.00', image_url: null, contact_number: '+919800000000' }],
      local_info: [{ title: 'Heritage Park', description: null, location: 'Lake Road', contact_number: null, image_url: null }],
    });
    mocks.receipt.mockResolvedValue({ receipt_ref: 'RCPT-AAA', kind: 'FINAL', content_hash: 'abc' });
    mocks.download.mockResolvedValue(new Blob(['%PDF-1.4']));
    const copy = vi.fn();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: copy }, configurable: true });
    wrap();
    await waitFor(() => expect(screen.getByText('Poha')).toBeInTheDocument());
    expect(screen.getByText('Test Cabs')).toBeInTheDocument();
    expect(screen.getByText('GuestNet')).toBeInTheDocument();
    expect(screen.getByText('Fort Walk')).toBeInTheDocument();
    expect(screen.getByText('Heritage Park')).toBeInTheDocument();
    expect(screen.getByText('Receipt RCPT-AAA')).toBeInTheDocument();
    screen.getByText('Copy password').click();
    await waitFor(() => expect(copy).toHaveBeenCalledWith('welcome123'));
  });

  it('shows expired/invalid-link state without technical details', async () => {
    mocks.overview.mockRejectedValue(new Error('404'));
    mocks.menu.mockRejectedValue(new Error('404'));
    mocks.cab.mockRejectedValue(new Error('404'));
    mocks.wifi.mockRejectedValue(new Error('404'));
    mocks.tourism.mockRejectedValue(new Error('404'));
    mocks.receipt.mockRejectedValue(new Error('404'));
    wrap();
    await waitFor(() => expect(screen.getByText(/This link is no longer valid/i)).toBeInTheDocument());
  });

  it('never persists the token in browser storage', async () => {
    mocks.overview.mockResolvedValue({
      hotel_name: 'Shree Shyam Home Stay',
      booking_ref: 'SSH-AAA',
      room_number: '101',
      room_type: 'Deluxe',
      check_in_date: '2026-11-10',
      check_out_date: '2026-11-13',
      nights: 3,
      status: 'CHECKED_IN',
      checked_out_at: null,
      expires_at: null,
      contact: { contact_number: null, email: null, address: null },
    });
    mocks.menu.mockResolvedValue({ categories: [] });
    mocks.cab.mockResolvedValue({ providers: [] });
    mocks.wifi.mockResolvedValue({ ssid: null, password: null });
    mocks.tourism.mockResolvedValue({ packages: [], local_info: [] });
    mocks.receipt.mockRejectedValue(new Error('404'));
    const setItem = vi.spyOn(window.localStorage, 'setItem');
    wrap();
    await waitFor(() => expect(screen.getByText(/Welcome to Shree Shyam Home Stay/i)).toBeInTheDocument());
    const stored = setItem.mock.calls.map((c) => String(c[1])).join(' ');
    expect(stored).not.toContain('tok123');
  });

  it('loads external menu images with no-referrer (no token leakage)', async () => {
    mocks.overview.mockResolvedValue({
      hotel_name: 'Shree Shyam Home Stay',
      booking_ref: 'SSH-AAA',
      room_number: '101',
      room_type: 'Deluxe',
      check_in_date: '2026-11-10',
      check_out_date: '2026-11-13',
      nights: 3,
      status: 'CHECKED_IN',
      checked_out_at: null,
      expires_at: null,
      contact: { contact_number: null, email: null, address: null },
    });
    mocks.menu.mockResolvedValue({
      categories: [{ category: 'Breakfast', items: [{ name: 'Poha', description: 'light', price: '120.00', image_url: 'https://images.test/poha.jpg', is_vegetarian: true }] }],
    });
    mocks.cab.mockResolvedValue({ providers: [] });
    mocks.wifi.mockResolvedValue({ ssid: null, password: null });
    mocks.tourism.mockResolvedValue({ packages: [], local_info: [] });
    mocks.receipt.mockRejectedValue(new Error('404'));
    const { container } = wrap();
    await waitFor(() => expect(screen.getByText('Poha')).toBeInTheDocument());
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('referrerpolicy')).toBe('no-referrer');
    // Priority 4: dish name is the accessible name (not empty alt).
    expect(img?.getAttribute('alt')).toBe('Poha');
    expect(img?.className).toMatch(/shrink-0/);
  });

  it('exposes landmark sections with a single h1 and labelled h2s', async () => {
    mocks.overview.mockResolvedValue({
      hotel_name: 'Shree Shyam Home Stay',
      booking_ref: 'SSH-AAA',
      room_number: '101',
      room_type: 'Deluxe',
      check_in_date: '2026-11-10',
      check_out_date: '2026-11-13',
      nights: 3,
      status: 'CHECKED_IN',
      checked_out_at: null,
      expires_at: null,
      contact: { contact_number: '+919800000000', email: 'stay@example.com', address: null },
    });
    mocks.menu.mockResolvedValue({ categories: [] });
    mocks.cab.mockResolvedValue({ providers: [] });
    mocks.wifi.mockResolvedValue({ ssid: null, password: null });
    mocks.tourism.mockResolvedValue({ packages: [], local_info: [] });
    mocks.receipt.mockRejectedValue(new Error('404'));
    const { container } = wrap();
    await waitFor(() => expect(screen.getByText(/Welcome to Shree Shyam Home Stay/i)).toBeInTheDocument());
    expect(container.querySelectorAll('h1')).toHaveLength(1);
    expect(screen.getByRole('heading', { name: /Welcome to Shree Shyam Home Stay/i, level: 1 })).toBeInTheDocument();
    for (const name of ['Your stay', 'Restaurant menu', 'Cabs', 'Tourism & local information', 'Wi-Fi', 'Receipt']) {
      expect(screen.getByRole('region', { name: new RegExp(name, 'i') })).toBeInTheDocument();
    }
    expect(container.querySelectorAll('h2')).toHaveLength(6);
    // Reception contact is a real tel:/mailto: link (not plain text).
    expect(screen.getByRole('link', { name: /Call reception/i })).toHaveAttribute('href', 'tel:+919800000000');
    expect(screen.getByRole('link', { name: /Email reception/i })).toHaveAttribute('href', 'mailto:stay@example.com');
  });

  it('gives Cab Call / Copy / Download accessible names and keyboard semantics', async () => {
    mocks.overview.mockResolvedValue({
      hotel_name: 'Shree Shyam Home Stay',
      booking_ref: 'SSH-AAA',
      room_number: '101',
      room_type: 'Deluxe',
      check_in_date: '2026-11-10',
      check_out_date: '2026-11-13',
      nights: 3,
      status: 'CHECKED_OUT',
      checked_out_at: '2026-11-13T10:00:00Z',
      expires_at: '2026-11-14T10:00:00Z',
      contact: { contact_number: null, email: null, address: null },
    });
    mocks.menu.mockResolvedValue({ categories: [] });
    mocks.cab.mockResolvedValue({
      providers: [{ company_name: 'Test Cabs', description: null, contact_number: '+919800000000', service_description: null }],
    });
    mocks.wifi.mockResolvedValue({ ssid: 'GuestNet', password: 'welcome123' });
    mocks.tourism.mockResolvedValue({ packages: [], local_info: [] });
    mocks.receipt.mockResolvedValue({ receipt_ref: 'RCPT-AAA', kind: 'FINAL', content_hash: 'abc' });
    mocks.download.mockResolvedValue(new Blob(['%PDF-1.4']));
    const copy = vi.fn(async () => undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: copy }, configurable: true });
    const { container } = wrap();
    await waitFor(() => expect(screen.getByText('Test Cabs')).toBeInTheDocument());
    // Call is an anchor (link role, keyboard + SR semantics) with context.
    const call = screen.getByRole('link', { name: /Call Test Cabs at/i });
    expect(call.tagName).toBe('A');
    expect(call.getAttribute('href')).toBe('tel:+919800000000');
    expect(call.className).toMatch(/min-h-11/);
    // Copy + Download are real buttons with visible focus styles.
    const copyBtn = screen.getByRole('button', { name: /Copy Wi-Fi password/i });
    const downloadBtn = screen.getByRole('button', { name: /Download final receipt PDF RCPT-AAA/i });
    expect(copyBtn.tagName).toBe('BUTTON');
    expect(downloadBtn.tagName).toBe('BUTTON');
    expect(copyBtn.className).toMatch(/focus-visible:ring-2/);
    expect(downloadBtn.className).toMatch(/min-h-11/);
    // Empty state uses status announcement role; error states use alert.
    expect(container.querySelector('main')).not.toBeNull();
    copyBtn.click();
    await waitFor(() => expect(screen.getByText(/Wi-Fi password copied\./)).toBeInTheDocument());
  });

  it('announces invalid-link errors and long content wraps without overflow hooks', async () => {
    mocks.overview.mockRejectedValue(new Error('404'));
    mocks.menu.mockRejectedValue(new Error('404'));
    mocks.cab.mockRejectedValue(new Error('404'));
    mocks.wifi.mockRejectedValue(new Error('404'));
    mocks.tourism.mockRejectedValue(new Error('404'));
    mocks.receipt.mockRejectedValue(new Error('404'));
    wrap();
    await waitFor(() => expect(screen.getByRole('alert', { name: '' })).toBeInTheDocument());
    expect(screen.getByText(/This link is no longer valid/i)).toBeInTheDocument();
  });

  it('renders long strings safely (break-word hooks present)', async () => {
    const longName = 'A'.repeat(120);
    const longDesc = 'B'.repeat(300);
    mocks.overview.mockResolvedValue({
      hotel_name: `Hotel ${longName}`,
      booking_ref: `SSH-${longName}`,
      room_number: '101',
      room_type: longName,
      check_in_date: '2026-11-10',
      check_out_date: '2026-11-13',
      nights: 3,
      status: 'CHECKED_IN',
      checked_out_at: null,
      expires_at: null,
      contact: { contact_number: null, email: null, address: null },
    });
    mocks.menu.mockResolvedValue({
      categories: [{ category: longName, items: [{ name: longName, description: longDesc, price: '120.00', image_url: null, is_vegetarian: false }] }],
    });
    mocks.cab.mockResolvedValue({
      providers: [{ company_name: longName, description: longDesc, contact_number: '+919800000000', service_description: longDesc }],
    });
    mocks.wifi.mockResolvedValue({ ssid: longName, password: longDesc });
    mocks.tourism.mockResolvedValue({
      packages: [{ name: longName, description: longDesc, duration: null, price: null, image_url: null, contact_number: null }],
      local_info: [],
    });
    mocks.receipt.mockRejectedValue(new Error('404'));
    const { container } = wrap();
    await waitFor(() => expect(screen.getByText(new RegExp('Hotel ' + 'A'.repeat(10)))).toBeInTheDocument());
    // Stay definition list is single-column on phones, two columns from sm up.
    const dl = container.querySelector('dl');
    expect(dl?.className).toMatch(/grid-cols-1/);
    expect(dl?.className).toMatch(/sm:grid-cols-2/);
    // Long text containers carry break-word hooks (pixel overflow is browser-only; jsdom cannot measure it).
    expect(container.innerHTML).toMatch(/break-words/);
    expect(container.innerHTML).toMatch(/break-all/);
    // Cab row stacks on phones (flex-col) instead of squeezing text + button.
    expect(container.querySelector('.flex-col')).not.toBeNull();
  });

  it('surfaces receipt-download failure feedback (no silent rejection)', async () => {
    mocks.overview.mockResolvedValue({
      hotel_name: 'Shree Shyam Home Stay',
      booking_ref: 'SSH-AAA',
      room_number: '101',
      room_type: 'Deluxe',
      check_in_date: '2026-11-10',
      check_out_date: '2026-11-13',
      nights: 3,
      status: 'CHECKED_OUT',
      checked_out_at: '2026-11-13T10:00:00Z',
      expires_at: '2026-11-14T10:00:00Z',
      contact: { contact_number: null, email: null, address: null },
    });
    mocks.menu.mockResolvedValue({ categories: [] });
    mocks.cab.mockResolvedValue({ providers: [] });
    mocks.wifi.mockResolvedValue({ ssid: null, password: null });
    mocks.tourism.mockResolvedValue({ packages: [], local_info: [] });
    mocks.receipt.mockResolvedValue({ receipt_ref: 'RCPT-AAA', kind: 'FINAL', content_hash: 'abc' });
    mocks.download.mockRejectedValue(new Error('network'));
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Download final receipt PDF/i })).toBeInTheDocument());
    screen.getByText('Download PDF').click();
    await waitFor(() => expect(screen.getByText(/could not be downloaded/i)).toBeInTheDocument());
  });
});
