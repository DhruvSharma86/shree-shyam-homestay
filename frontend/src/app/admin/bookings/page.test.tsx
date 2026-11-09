import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import BookingsPage from '@/app/admin/bookings/page';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  recordPayment: vi.fn(),
  checkIn: vi.fn(),
  rotatePortal: vi.fn(),
  revokePortal: vi.fn(),
}));

vi.mock('@/services/tourism', () => ({
  bookingsApi: {
    list: () => mocks.list(),
    get: (id: string) => mocks.get(id),
    recordCheckInPayment: (id: string, b: unknown) => mocks.recordPayment(id, b),
    checkIn: (id: string) => mocks.checkIn(id),
    rotatePortal: (id: string) => mocks.rotatePortal(id),
    revokePortal: (id: string) => mocks.revokePortal(id),
  },
  tourismApi: {},
  downloadStaffReceipt: vi.fn(),
}));

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <BookingsPage />
    </QueryClientProvider>,
  );
}

describe('bookings check-in link delivery', () => {
  it('shows the one-time link once and copies it', async () => {
    mocks.list.mockResolvedValue({
      items: [
        { id: 'b1', booking_ref: 'SSH-AAA', status: 'CONFIRMED', check_in_date: '2026-11-10', check_out_date: '2026-11-11', nights: 1 },
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });
    mocks.get.mockResolvedValue({
      id: 'b1',
      booking_ref: 'SSH-AAA',
      status: 'CONFIRMED',
      check_in_date: '2026-11-10',
      check_out_date: '2026-11-11',
      nights: 1,
      guest_id: 'g1',
      room_id: 'r1',
      room_type_id: 't1',
      source: 'PHONE',
      number_of_guests: 1,
      notes: null,
      night_rate_snapshot: '2500.00',
      rate_id: null,
      room_subtotal: '2500.00',
      tax_type_snapshot: 'NONE',
      tax_rate_snapshot: null,
      tax_pricing_mode_snapshot: 'EXCLUSIVE',
      total_amount: '2500.00',
      cancelled_at: null,
      cancellation_reason: null,
    });
    mocks.checkIn.mockResolvedValue({ booking_id: 'b1', booking_ref: 'SSH-AAA', status: 'CHECKED_IN', checked_in_at: 'now', portal_access_token: 'SECRET123' });
    mocks.recordPayment.mockResolvedValue({});
    const copy = vi.fn();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: copy }, configurable: true });
    wrap();
    await waitFor(() => expect(screen.getByText('SSH-AAA')).toBeInTheDocument());
    screen.getByText('Open').click();
    await waitFor(() => expect(screen.getByText(/Record one-night payment/)).toBeInTheDocument());
    fireEvent.click(screen.getByText('Check in & issue guest link'));
    await waitFor(() => expect(screen.getByText(/shown once/)).toBeInTheDocument());
    expect(screen.getByText(/SECRET123/)).toBeInTheDocument();
  });
});
