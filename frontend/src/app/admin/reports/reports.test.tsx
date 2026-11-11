import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ReportsPage from '@/app/admin/reports/page';
import { useAuthStore } from '@/stores/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/admin/reports',
}));

const reports = vi.hoisted(() => ({
  financialSummary: vi.fn(),
  collections: vi.fn(),
  collectionsExport: vi.fn(),
  paymentMethods: vi.fn(),
  outstanding: vi.fn(),
  outstandingExport: vi.fn(),
  reconciliation: vi.fn(),
  reversals: vi.fn(),
  bookingsSummary: vi.fn(),
  occupancy: vi.fn(),
}));

vi.mock('@/services/reports', () => ({
  reportsApi: {
    financialSummary: (from_date?: string, to_date?: string) => reports.financialSummary(from_date, to_date),
    collections: (from_date?: string, to_date?: string) => reports.collections(from_date, to_date),
    collectionsExport: (from_date?: string, to_date?: string) => reports.collectionsExport(from_date, to_date),
    paymentMethods: (from_date?: string, to_date?: string) => reports.paymentMethods(from_date, to_date),
    outstanding: (page = 1, page_size = 50) => reports.outstanding(page, page_size),
    outstandingExport: () => reports.outstandingExport(),
    reconciliation: (from_date?: string, to_date?: string) => reports.reconciliation(from_date, to_date),
    reversals: (from_date?: string, to_date?: string, page = 1, page_size = 50) => reports.reversals(from_date, to_date, page, page_size),
    bookingsSummary: (from_date?: string, to_date?: string) => reports.bookingsSummary(from_date, to_date),
    occupancy: (from_date?: string, to_date?: string) => reports.occupancy(from_date, to_date),
  },
  downloadCollectionsCsv: vi.fn(),
  downloadOutstandingCsv: vi.fn(),
}));

function setRole(username: string, role: 'ADMIN' | 'RECEPTIONIST', permissions: string[]) {
  useAuthStore.setState({
    me: { user: { username, role, full_name: 'U' } as never, permissions } as never,
    loading: false,
  });
}

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ReportsPage /></QueryClientProvider>
  );
}

const SUMMARY = {
  from_date: '2026-01-01',
  to_date: '2026-01-31',
  room_charges: 50000.00,
  additional_charges: 5000.00,
  discounts: 2000.00,
  charge_reversals: 500.00,
  gross_charges: 55000.00,
  net_payments: 52000.00,
  outstanding: 3000.00,
};

const COLLECTIONS = {
  from_date: '2026-01-01',
  to_date: '2026-01-31',
  rows: [
    { date: '2026-01-01', method: 'CASH', stage: 'CHECK_IN', transactions: 2, original_total: 5000.00, reversal_total: 0, net_total: 5000.00 },
    { date: '2026-01-02', method: 'UPI', stage: 'CHECKOUT', transactions: 1, original_total: 3000.00, reversal_total: 0, net_total: 3000.00 },
  ],
  original_total: 8000.00,
  reversal_total: 0.00,
  net_total: 8000.00,
};

const METHODS = {
  from_date: '2026-01-01',
  to_date: '2026-01-31',
  rows: [
    { method: 'CASH', transactions: 5, original_total: 20000.00, reversal_total: 0, net_total: 20000.00 },
    { method: 'UPI', transactions: 3, original_total: 15000.00, reversal_total: 0, net_total: 15000.00 },
    { method: 'CARD_POS', transactions: 2, original_total: 10000.00, reversal_total: 0, net_total: 10000.00 },
  ],
  original_total: 45000.00,
  reversal_total: 0.00,
  net_total: 45000.00,
};

const BOOKINGS = {
  from_date: '2026-01-01',
  to_date: '2026-01-31',
  total: 10,
  confirmed: 4,
  checked_in: 3,
  checked_out: 2,
  cancelled: 1,
};

const OCCUPANCY = {
  from_date: '2026-01-01',
  to_date: '2026-01-31',
  occupied_room_nights: 62,
  available_room_nights: 310,
  occupancy_rate: 20.00,
};

const OUTSTANDING = {
  snapshot: 'live-current',
  rows: [
    { booking_id: 'b1', booking_ref: 'SSH-001', room_number: '101', status: 'CONFIRMED', total_charges: 5000.00, net_paid: 2000.00, balance: 3000.00 },
    { booking_id: 'b2', booking_ref: 'SSH-002', room_number: '102', status: 'CHECKED_IN', total_charges: 8000.00, net_paid: 9000.00, balance: -1000.00 },
  ],
  outstanding_total: 3000.00,
  credit_total: 1000.00,
  total: 2,
  page: 1,
  page_size: 50,
};

const REVERSALS = {
  from_date: '2026-01-01',
  to_date: '2026-01-31',
  payment_reversal_total: 500.00,
  charge_reversal_total: 300.00,
  items: [
    { kind: 'charge', id: 'e1', booking_id: 'b1', booking_ref: 'SSH-001', amount: -300.00, reason: 'Duplicate charge', reverses_id: 'e0', created_at: '2026-01-10T10:00:00Z' },
    { kind: 'payment', id: 'p1', booking_id: 'b2', booking_ref: 'SSH-002', amount: 500.00, reason: 'Failed UPI', reverses_id: 'p0', created_at: '2026-01-12T14:00:00Z' },
  ],
  total: 2,
  page: 1,
  page_size: 50,
};

const RECONCILIATION = {
  from_date: '2026-01-01',
  to_date: '2026-01-31',
  charge_entries: 55000.00,
  original_payments: 52500.00,
  reversal_payments: 500.00,
  net_payments: 52000.00,
  outstanding_in_period: 3000.00,
  credit_in_period: 0.00,
  entry_count: 15,
  payment_count: 10,
  reversal_count: 1,
};

function mockAllReports() {
  reports.financialSummary.mockResolvedValue(SUMMARY);
  reports.collections.mockResolvedValue(COLLECTIONS);
  reports.paymentMethods.mockResolvedValue(METHODS);
  reports.bookingsSummary.mockResolvedValue(BOOKINGS);
  reports.occupancy.mockResolvedValue(OCCUPANCY);
  reports.outstanding.mockResolvedValue(OUTSTANDING);
  reports.reversals.mockResolvedValue(REVERSALS);
  reports.reconciliation.mockResolvedValue(RECONCILIATION);
}

beforeEach(() => {
  vi.clearAllMocks();
  setRole('admin1', 'ADMIN', ['reports.financial.read', 'users.manage']);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('reports page — admin access', () => {
  it('loads and displays financial summary', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText('Reports & Analytics')).toBeInTheDocument());
    const grossCards = screen.getAllByText('₹55,000.00');
    expect(grossCards.length).toBeGreaterThanOrEqual(1);
    const netCards = screen.getAllByText('₹52,000.00');
    expect(netCards.length).toBeGreaterThanOrEqual(1);
    const outstandingCards = screen.getAllByText('₹3,000.00');
    expect(outstandingCards.length).toBeGreaterThanOrEqual(1);
  });

  it('shows period label with selected dates', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText(/All time/)).toBeInTheDocument());
  });

  it('displays booking status breakdown', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText('Confirmed')).toBeInTheDocument());
    const countEls = screen.getAllByText('4');
    expect(countEls.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('displays occupancy rate', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText('20%')).toBeInTheDocument());
  });

  it('displays payment method breakdown', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText('CASH')).toBeInTheDocument());
    expect(screen.getByText('UPI')).toBeInTheDocument();
    expect(screen.getByText('CARD_POS')).toBeInTheDocument();
  });

  it('displays outstanding balances table', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText('Outstanding Balances')).toBeInTheDocument());
    const b1Els = screen.queryAllByText('SSH-001');
    expect(b1Els.length).toBeGreaterThanOrEqual(1);
    const b2Els = screen.queryAllByText('SSH-002');
    expect(b2Els.length).toBeGreaterThanOrEqual(1);
  });

  it('displays reversals table', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText('Duplicate charge')).toBeInTheDocument());
    expect(screen.getByText('Failed UPI')).toBeInTheDocument();
  });

  it('displays reconciliation figures', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText('Charge entries')).toBeInTheDocument());
    expect(screen.getByText('Original payments')).toBeInTheDocument();
  });

  it('downloads collections CSV', async () => {
    const { downloadCollectionsCsv } = await import('@/services/reports');
    vi.mocked(downloadCollectionsCsv).mockResolvedValue(new Blob(['a,b'], { type: 'text/csv' }));
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText('Reports & Analytics')).toBeInTheDocument());
    const csvButtons = screen.getAllByText('Download CSV');
    fireEvent.click(csvButtons[0]);
    await waitFor(() => expect(downloadCollectionsCsv).toHaveBeenCalled());
  });

  it('shows empty state for collections chart', async () => {
    reports.financialSummary.mockResolvedValue(SUMMARY);
    reports.collections.mockResolvedValue({ ...COLLECTIONS, rows: [], original_total: 0, reversal_total: 0, net_total: 0 });
    reports.paymentMethods.mockResolvedValue(METHODS);
    reports.bookingsSummary.mockResolvedValue(BOOKINGS);
    reports.occupancy.mockResolvedValue(OCCUPANCY);
    reports.outstanding.mockResolvedValue(OUTSTANDING);
    reports.reversals.mockResolvedValue(REVERSALS);
    reports.reconciliation.mockResolvedValue(RECONCILIATION);
    wrap();
    await waitFor(() => expect(screen.getByText('No data for selected period')).toBeInTheDocument());
  });

  it('shows empty state for outstanding', async () => {
    reports.financialSummary.mockResolvedValue(SUMMARY);
    reports.collections.mockResolvedValue(COLLECTIONS);
    reports.paymentMethods.mockResolvedValue(METHODS);
    reports.bookingsSummary.mockResolvedValue(BOOKINGS);
    reports.occupancy.mockResolvedValue(OCCUPANCY);
    reports.outstanding.mockResolvedValue({ ...OUTSTANDING, rows: [], outstanding_total: 0, credit_total: 0, total: 0 });
    reports.reversals.mockResolvedValue(REVERSALS);
    reports.reconciliation.mockResolvedValue(RECONCILIATION);
    wrap();
    await waitFor(() => expect(screen.getByText('No outstanding balances')).toBeInTheDocument());
  });

  it('shows empty state for reversals', async () => {
    reports.financialSummary.mockResolvedValue(SUMMARY);
    reports.collections.mockResolvedValue(COLLECTIONS);
    reports.paymentMethods.mockResolvedValue(METHODS);
    reports.bookingsSummary.mockResolvedValue(BOOKINGS);
    reports.occupancy.mockResolvedValue(OCCUPANCY);
    reports.outstanding.mockResolvedValue(OUTSTANDING);
    reports.reversals.mockResolvedValue({ ...REVERSALS, items: [], payment_reversal_total: 0, charge_reversal_total: 0, total: 0 });
    reports.reconciliation.mockResolvedValue(RECONCILIATION);
    wrap();
    await waitFor(() => expect(screen.getByText('No reversals')).toBeInTheDocument());
  });
});

describe('reports page — date filters', () => {
  it('has date input fields', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByLabelText('From date')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByLabelText('To date')).toBeInTheDocument());
  });

  it('accepts date input changes', async () => {
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByLabelText('From date')).toBeInTheDocument());
    const fromInput = screen.getByLabelText('From date');
    const toInput = screen.getByLabelText('To date');
    fireEvent.change(fromInput, { target: { value: '2026-01-01' } });
    fireEvent.change(toInput, { target: { value: '2026-01-31' } });
    expect(fromInput).toHaveValue('2026-01-01');
    expect(toInput).toHaveValue('2026-01-31');
  });
});

describe('reports page — API error handling', () => {
  it('shows error when financial summary fails', async () => {
    reports.financialSummary.mockRejectedValue(new Error('Server error'));
    reports.collections.mockResolvedValue(COLLECTIONS);
    reports.paymentMethods.mockResolvedValue(METHODS);
    reports.bookingsSummary.mockResolvedValue(BOOKINGS);
    reports.occupancy.mockResolvedValue(OCCUPANCY);
    reports.outstanding.mockResolvedValue(OUTSTANDING);
    reports.reversals.mockResolvedValue(REVERSALS);
    reports.reconciliation.mockResolvedValue(RECONCILIATION);
    wrap();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('retry button refetches all queries', async () => {
    reports.financialSummary.mockRejectedValueOnce(new Error('Server error')).mockResolvedValue(SUMMARY);
    reports.collections.mockResolvedValue(COLLECTIONS);
    reports.paymentMethods.mockResolvedValue(METHODS);
    reports.bookingsSummary.mockResolvedValue(BOOKINGS);
    reports.occupancy.mockResolvedValue(OCCUPANCY);
    reports.outstanding.mockResolvedValue(OUTSTANDING);
    reports.reversals.mockResolvedValue(REVERSALS);
    reports.reconciliation.mockResolvedValue(RECONCILIATION);
    wrap();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Retry'));
    await waitFor(() => {
      const cards = screen.getAllByText('₹55,000.00');
      expect(cards.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe('reports page — receptionist restrictions', () => {
  it('denies access to receptionists without reports permission', async () => {
    setRole('rec1', 'RECEPTIONIST', ['bookings.read', 'bookings.write', 'billing.charges.write', 'billing.payments.write', 'billing.receipts.read']);
    mockAllReports();
    wrap();
    await waitFor(() => expect(screen.getByText(/do not have permission/)).toBeInTheDocument());
    expect(screen.getByText(/reports.financial.read/)).toBeInTheDocument();
  });

  it('receptionist shell does not show Reports navigation', async () => {
    setRole('rec1', 'RECEPTIONIST', ['bookings.read']);
    const { AdminShell } = await import('@/components/AdminShell');
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AdminShell><p>content</p></AdminShell>
      </QueryClientProvider>
    );
    expect(screen.queryByText('Reports')).not.toBeInTheDocument();
  });
});
