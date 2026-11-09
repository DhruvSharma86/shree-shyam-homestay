import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import BookingsPage from '@/app/admin/bookings/page';
import { AdminShell } from '@/components/AdminShell';
import { useAuthStore } from '@/stores/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/admin/bookings',
}));

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

function setRole(username: string, role: 'ADMIN' | 'RECEPTIONIST', permissions: string[]) {
  useAuthStore.setState({
    me: { user: { username, role, full_name: 'U' } as never, permissions } as never,
    loading: false,
  });
}

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <BookingsPage />
    </QueryClientProvider>,
  );
}

const LIST = {
  items: [
    { id: 'b1', booking_ref: 'SSH-AAA', status: 'CONFIRMED', check_in_date: '2026-11-10', check_out_date: '2026-11-11', nights: 1 },
  ],
  total: 1,
  page: 1,
  page_size: 50,
};

const DETAIL = {
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
};

describe('bookings page roles', () => {
  it('receptionist can open, pay, check in and copy the link', async () => {
    setRole('rec1', 'RECEPTIONIST', ['bookings.read', 'bookings.checkin', 'billing.payments.write']);
    mocks.list.mockResolvedValue(LIST);
    mocks.get.mockResolvedValue(DETAIL);
    mocks.recordPayment.mockResolvedValue({});
    mocks.checkIn.mockResolvedValue({ booking_id: 'b1', booking_ref: 'SSH-AAA', status: 'CHECKED_IN', checked_in_at: 'now', portal_access_token: 'SECRET-REC' });
    const copy = vi.fn();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: copy }, configurable: true });
    wrap();
    await waitFor(() => expect(screen.getByText('SSH-AAA')).toBeInTheDocument());
    screen.getByText('Open').click();
    await waitFor(() => expect(screen.getByText(/Record one-night payment/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText('2500.00'), { target: { value: '2500.00' } });
    fireEvent.click(screen.getByText('Record one-night payment'));
    await waitFor(() => expect(mocks.recordPayment).toHaveBeenCalled());
    fireEvent.click(screen.getByText('Check in & issue guest link'));
    await waitFor(() => expect(screen.getByText(/SECRET-REC/)).toBeInTheDocument());
    fireEvent.click(screen.getByText('Copy link'));
    await waitFor(() => expect(copy).toHaveBeenCalledWith(expect.stringContaining('/guest/SECRET-REC')));
    // Token token trajectory: dismissal clears the token; it is not persisted anywhere.
    expect(mocks.rotatePortal).not.toHaveBeenCalled();
    expect(mocks.revokePortal).not.toHaveBeenCalled();
    expect(screen.queryByText(/Rotate link \(ADMIN\)/)).not.toBeInTheDocument();
  });

  it('admin sees rotate/revoke controls and uses them', async () => {
    setRole('admin1', 'ADMIN', ['users.manage', 'portal.tokens.manage']);
    mocks.list.mockResolvedValue(LIST);
    mocks.get.mockResolvedValue({ ...DETAIL, status: 'CHECKED_IN' });
    mocks.rotatePortal.mockResolvedValue({ booking_id: 'b1', portal_access_token: 'SECRET-ADM' });
    mocks.revokePortal.mockResolvedValue({});
    wrap();
    await waitFor(() => expect(screen.getByText('SSH-AAA')).toBeInTheDocument());
    screen.getByText('Open').click();
    await waitFor(() => expect(screen.getByText('Rotate link (ADMIN)')).toBeInTheDocument());
    expect(screen.getByText('Revoke link (ADMIN)')).toBeInTheDocument();
  });

  it('receptionist shell hides admin navigation', () => {
    setRole('rec1', 'RECEPTIONIST', ['bookings.read']);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AdminShell><p>content</p></AdminShell>
      </QueryClientProvider>,
    );
    expect(screen.getByText('Bookings')).toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.queryByText('Tourism')).not.toBeInTheDocument();
    expect(screen.queryByText('Users')).not.toBeInTheDocument();
  });

  it('receptionist sees recovery guidance after check-in', async () => {
    setRole('rec1', 'RECEPTIONIST', ['bookings.read', 'bookings.checkin', 'billing.payments.write']);
    mocks.list.mockResolvedValue(LIST);
    mocks.get.mockResolvedValue({ ...DETAIL, status: 'CHECKED_IN' });
    mocks.recordPayment.mockResolvedValue({});
    mocks.checkIn.mockResolvedValue({ booking_id: 'b1', booking_ref: 'SSH-AAA', status: 'CHECKED_IN', checked_in_at: 'now', portal_access_token: 'SECRET-REC' });
    wrap();
    await waitFor(() => expect(screen.getByText('SSH-AAA')).toBeInTheDocument());
    screen.getByText('Open').click();
    await waitFor(() => expect(screen.getByText(/cannot be retrieved again/)).toBeInTheDocument());
    expect(screen.queryByText('Rotate link (ADMIN)')).not.toBeInTheDocument();
  });

  it('admin shell shows full navigation', () => {
    setRole('admin1', 'ADMIN', ['users.manage']);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AdminShell><p>content</p></AdminShell>
      </QueryClientProvider>,
    );
    expect(screen.getByText('Tourism')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
  });

  it('payment timeout explains the unknown outcome and never auto-retries', async () => {
    setRole('rec1', 'RECEPTIONIST', ['bookings.read', 'bookings.checkin', 'billing.payments.write']);
    mocks.list.mockResolvedValue(LIST);
    mocks.get.mockResolvedValue(DETAIL);
    const timeoutErr = new Error('timeout of 15000ms exceeded') as Error & {
      isAxiosError?: boolean;
      code?: string;
      response?: unknown;
      config: object;
      request: object;
    };
    timeoutErr.isAxiosError = true;
    timeoutErr.code = 'ECONNABORTED';
    timeoutErr.config = {};
    timeoutErr.request = {};
    mocks.recordPayment.mockRejectedValue(timeoutErr);
    mocks.checkIn.mockResolvedValue({});
    wrap();
    await waitFor(() => expect(screen.getByText('SSH-AAA')).toBeInTheDocument());
    screen.getByText('Open').click();
    await waitFor(() => expect(screen.getByText(/Record one-night payment/)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText('2500.00'), { target: { value: '2500.00' } });
    fireEvent.click(screen.getByText('Record one-night payment'));
    await waitFor(() => expect(mocks.recordPayment).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole('alert', { name: '' })).toBeInTheDocument());
    expect(screen.getByText(/Check the current booking state/i)).toBeInTheDocument();
    expect(mocks.recordPayment).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/SECRET-REC/)).not.toBeInTheDocument();
  });
});
