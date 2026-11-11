import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import FolioPage from '@/app/admin/bookings/folio';
import { useAuthStore } from '@/stores/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/admin/bookings/b1',
}));

const folio = vi.hoisted(() => ({
  get: vi.fn(),
  createCharge: vi.fn(),
  createDiscount: vi.fn(),
  createReversal: vi.fn(),
}));
const payments = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
}));
const bookings = vi.hoisted(() => ({
  receipt: vi.fn(),
}));
const download = vi.hoisted(() => vi.fn());

vi.mock('@/services/tourism', () => ({
  folioApi: {
    get: (id: string) => folio.get(id),
    createCharge: (id: string, b: unknown) => folio.createCharge(id, b),
    createDiscount: (id: string, b: unknown) => folio.createDiscount(id, b),
    createReversal: (id: string, b: unknown) => folio.createReversal(id, b),
  },
  paymentsApi: {
    list: (id: string, page = 1, page_size = 50) => payments.list(id, page, page_size),
    create: (id: string, b: unknown) => payments.create(id, b),
  },
  bookingsApi: {
    receipt: (id: string) => bookings.receipt(id),
  },
  downloadStaffReceipt: download,
}));

function setRole(username: string, role: 'ADMIN' | 'RECEPTIONIST', permissions: string[]) {
  useAuthStore.setState({
    me: { user: { username, role, full_name: 'U' } as never, permissions } as never,
    loading: false,
  });
}

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><FolioPage booking_id="b1" /></QueryClientProvider>,
  );
}

const FOLIO = {
  booking_id: 'b1',
  booking_ref: 'SSH-BBB',
  booking_status: 'CONFIRMED',
  entries: [
    {
      id: 'e1',
      booking_id: 'b1',
      entry_type: 'ROOM_CHARGE',
      description: 'Room Charge - 2 nights @ 2500.00',
      quantity: 2,
      unit_amount: 2500.00,
      amount: 5000.00,
      is_initial: true,
      reverses_entry_id: null,
      created_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'e2',
      booking_id: 'b1',
      entry_type: 'ADDITIONAL_CHARGE',
      description: 'Restaurant Dinner',
      quantity: 1,
      unit_amount: 500.00,
      amount: 500.00,
      is_initial: false,
      reverses_entry_id: null,
      created_at: '2026-01-02T00:00:00Z',
    },
  ],
  total_charges: 5500.00,
  total_paid: 2500.00,
  balance_due: 3000.00,
  payment_count: 1,
};

const PAYMENTS = {
  items: [
    {
      id: 'p1',
      booking_id: 'b1',
      amount: 2500.00,
      mode: 'CASH',
      payment_stage: 'CHECK_IN',
      reference_note: null,
      is_reversal: false,
      reverses_payment_id: null,
      received_at: '2026-01-01T10:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
};

const RECEIPT = {
  receipt_id: 'r1',
  booking_id: 'b1',
  receipt_ref: 'SSH-RCP-001',
  kind: 'FINAL',
  content_hash: 'sha256:abc123',
};

function axiosError(message: string, status: number): Error {
  const err: Error & { isAxiosError?: boolean; response?: { status: number; data: { error: { message: string } } } } = new Error(message);
  err.isAxiosError = true;
  err.response = { status, data: { error: { message } } };
  return err;
}

beforeEach(() => {
  vi.clearAllMocks();
  setRole('admin1', 'ADMIN', [
    'billing.charges.write',
    'billing.payments.write',
    'billing.discounts.write',
    'billing.receipts.read',
    'portal.tokens.manage',
  ]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('folio page — overview', () => {
  it('displays folio overview with charges and balance', async () => {
    folio.get.mockResolvedValue(FOLIO);
    payments.list.mockResolvedValue(PAYMENTS);
    wrap();
    await waitFor(() => expect(screen.getByText(/SSH-BBB/)).toBeInTheDocument());
    expect(screen.getByText('Room Charge - 2 nights @ 2500.00')).toBeInTheDocument();
    expect(screen.getByText('Restaurant Dinner')).toBeInTheDocument();
    expect(screen.getAllByText('5500.00')[0]).toBeInTheDocument();
    expect(screen.getAllByText('2500.00').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('3000.00')).toBeInTheDocument();
  });

  it('shows empty folio entries state', async () => {
    folio.get.mockResolvedValue({ ...FOLIO, entries: [] });
    wrap();
    await waitFor(() => expect(screen.getByText('No folio entries yet')).toBeInTheDocument());
  });

  it('shows error state when folio fails to load', async () => {
    folio.get.mockRejectedValue(new Error('boom'));
    wrap();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('displays payments history', async () => {
    folio.get.mockResolvedValue(FOLIO);
    payments.list.mockResolvedValue(PAYMENTS);
    wrap();
    await waitFor(() => expect(screen.getByText('CHECK_IN')).toBeInTheDocument());
  });

  it('shows empty payments state', async () => {
    folio.get.mockResolvedValue(FOLIO);
    payments.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    wrap();
    await waitFor(() => expect(screen.getByText('No payments yet')).toBeInTheDocument());
  });
});

describe('folio page — additional charges', () => {
  it('adds a charge successfully and refreshes folio', async () => {
    folio.get.mockResolvedValue(FOLIO);
    folio.createCharge.mockResolvedValue({
      id: 'e3',
      booking_id: 'b1',
      entry_type: 'ADDITIONAL_CHARGE',
      description: 'Room Service',
      quantity: 1,
      unit_amount: 1200.00,
      amount: 1200.00,
      is_initial: false,
      reverses_entry_id: null,
      created_at: '2026-01-03T00:00:00Z',
    });
    wrap();
    await waitFor(() => expect(screen.getByText('Room Charge - 2 nights @ 2500.00')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await waitFor(() => expect(screen.getByLabelText('Description')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Room Service' } });
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Unit Amount'), { target: { value: '1200.00' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await waitFor(() => expect(folio.createCharge).toHaveBeenCalledWith('b1', expect.objectContaining({ description: 'Room Service' })));
  });

  it('rejects empty charge description — mutation not called', async () => {
    folio.get.mockResolvedValue(FOLIO);
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Charge/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await waitFor(() => expect(screen.getByLabelText('Description')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await new Promise((r) => setTimeout(r, 50));
    expect(folio.createCharge).not.toHaveBeenCalled();
  });

  it('rejects zero quantity — mutation not called', async () => {
    folio.get.mockResolvedValue(FOLIO);
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Charge/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await waitFor(() => expect(screen.getByLabelText('Description')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Test Charge' } });
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await new Promise((r) => setTimeout(r, 50));
    expect(folio.createCharge).not.toHaveBeenCalled();
  });

  it('rejects negative unit amount — mutation not called', async () => {
    folio.get.mockResolvedValue(FOLIO);
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Charge/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await waitFor(() => expect(screen.getByLabelText('Description')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Test Charge' } });
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Unit Amount'), { target: { value: '-100' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await new Promise((r) => setTimeout(r, 50));
    expect(folio.createCharge).not.toHaveBeenCalled();
  });

  it('handles API error when adding charge', async () => {
    folio.get.mockResolvedValue(FOLIO);
    folio.createCharge.mockRejectedValue(axiosError('Folio is closed', 409));
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Charge/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await waitFor(() => expect(screen.getByLabelText('Description')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Test Charge' } });
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Unit Amount'), { target: { value: '100' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Charge/ }));
    await waitFor(() => expect(screen.getByText(/Folio is closed/)).toBeInTheDocument());
  });
});

describe('folio page — discounts', () => {
  it('allows ADMIN to add a discount', async () => {
    folio.get.mockResolvedValue(FOLIO);
    folio.createDiscount.mockResolvedValue({
      id: 'e3',
      booking_id: 'b1',
      entry_type: 'DISCOUNT',
      description: 'Loyalty discount',
      quantity: 1,
      unit_amount: -500.00,
      amount: -500.00,
      is_initial: false,
      reverses_entry_id: null,
      created_at: '2026-01-03T00:00:00Z',
    });
    wrap();
    await waitFor(() => expect(screen.getByText('Room Charge - 2 nights @ 2500.00')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Add Discount/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Discount/ })).toBeInTheDocument());
    // Discount form Amount is the first Amount field (discount form renders before payment form)
    const amountInputs = screen.getAllByLabelText('Amount');
    fireEvent.change(amountInputs[0], { target: { value: '500.00' } });
    const reasonInputs = screen.getAllByLabelText('Reason');
    fireEvent.change(reasonInputs[reasonInputs.length - 1], { target: { value: 'Loyalty discount' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Discount/ }));
    await waitFor(() => expect(folio.createDiscount).toHaveBeenCalledWith('b1', expect.objectContaining({ amount: 500, reason: 'Loyalty discount' })));
  });

  it('rejects invalid discount amount — mutation not called', async () => {
    folio.get.mockResolvedValue(FOLIO);
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Discount/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Add Discount/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Discount/ })).toBeInTheDocument());
    const amountInputs = screen.getAllByLabelText('Amount');
    fireEvent.change(amountInputs[0], { target: { value: '-100' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Discount/ }));
    await new Promise((r) => setTimeout(r, 50));
    expect(folio.createDiscount).not.toHaveBeenCalled();
  });

  it('requires discount reason — mutation not called', async () => {
    folio.get.mockResolvedValue(FOLIO);
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Discount/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Add Discount/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Discount/ })).toBeInTheDocument());
    const amountInputs = screen.getAllByLabelText('Amount');
    fireEvent.change(amountInputs[0], { target: { value: '500.00' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Discount/ }));
    await new Promise((r) => setTimeout(r, 50));
    expect(folio.createDiscount).not.toHaveBeenCalled();
  });

  it('handles API error when adding discount', async () => {
    folio.get.mockResolvedValue(FOLIO);
    folio.createDiscount.mockRejectedValue(axiosError('Discount rejected', 422));
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Discount/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Add Discount/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Discount/ })).toBeInTheDocument());
    const amountInputs = screen.getAllByLabelText('Amount');
    fireEvent.change(amountInputs[0], { target: { value: '500.00' } });
    const reasonInputs = screen.getAllByLabelText('Reason');
    fireEvent.change(reasonInputs[reasonInputs.length - 1], { target: { value: 'Test reason' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Discount/ }));
    await waitFor(() => expect(screen.getByText(/Discount rejected/)).toBeInTheDocument());
  });
});

describe('folio page — discounts permission enforcement', () => {
  it('hides discount option for receptionist', async () => {
    setRole('rec1', 'RECEPTIONIST', [
      'billing.charges.write',
      'billing.payments.write',
      'billing.receipts.read',
    ]);
    folio.get.mockResolvedValue(FOLIO);
    wrap();
    await waitFor(() => expect(screen.getByText('Room Charge - 2 nights @ 2500.00')).toBeInTheDocument());
    expect(screen.queryByText(/Add Discount/)).not.toBeInTheDocument();
    expect(screen.getByText(/Discounts are ADMIN-only/)).toBeInTheDocument();
  });
});

describe('folio page — reversals', () => {
  it('reverses an entry successfully', async () => {
    folio.get.mockResolvedValue(FOLIO);
    folio.createReversal.mockResolvedValue({
      id: 'e3',
      booking_id: 'b1',
      entry_type: 'REVERSAL',
      description: 'Reversal of Restaurant Dinner',
      quantity: 1,
      unit_amount: -500.00,
      amount: -500.00,
      is_initial: false,
      reverses_entry_id: 'e2',
      created_at: '2026-01-03T00:00:00Z',
    });
    wrap();
    await waitFor(() => expect(screen.getByText('Restaurant Dinner')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Reverse Entry/ }));
    await waitFor(() => expect(screen.getByLabelText('Entry ID to reverse')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Entry ID to reverse'), { target: { value: 'e2' } });
    fireEvent.click(screen.getByRole('button', { name: /Reverse Entry/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Confirm Reversal/ })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Customer complaint' } });
    fireEvent.click(screen.getByRole('button', { name: /Confirm Reversal/ }));
    await waitFor(() => expect(folio.createReversal).toHaveBeenCalledWith('b1', expect.objectContaining({ entry_id: 'e2', reason: 'Customer complaint' })));
  });

  it('requires reversal reason — mutation not called', async () => {
    folio.get.mockResolvedValue(FOLIO);
    wrap();
    await waitFor(() => expect(screen.getByText('Restaurant Dinner')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Reverse Entry/ }));
    await waitFor(() => expect(screen.getByLabelText('Entry ID to reverse')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Entry ID to reverse'), { target: { value: 'e2' } });
    fireEvent.click(screen.getByRole('button', { name: /Reverse Entry/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Confirm Reversal/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Confirm Reversal/ }));
    await new Promise((r) => setTimeout(r, 50));
    expect(folio.createReversal).not.toHaveBeenCalled();
  });

  it('handles API error when reversing', async () => {
    folio.get.mockResolvedValue(FOLIO);
    folio.createReversal.mockRejectedValue(axiosError('Cannot reverse initial entry', 422));
    wrap();
    await waitFor(() => expect(screen.getByText('Restaurant Dinner')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Reverse Entry/ }));
    await waitFor(() => expect(screen.getByLabelText('Entry ID to reverse')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Entry ID to reverse'), { target: { value: 'e1' } });
    fireEvent.click(screen.getByRole('button', { name: /Reverse Entry/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Confirm Reversal/ })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Test reason' } });
    fireEvent.click(screen.getByRole('button', { name: /Confirm Reversal/ }));
    await waitFor(() => expect(screen.getByText(/Cannot reverse initial entry/)).toBeInTheDocument());
  });
});

describe('folio page — payments', () => {
  it('records a CASH payment at CHECK_IN stage', async () => {
    folio.get.mockResolvedValue(FOLIO);
    payments.list.mockResolvedValue(PAYMENTS);
    payments.create.mockResolvedValue({
      id: 'p2',
      booking_id: 'b1',
      amount: 3000.00,
      mode: 'CASH',
      payment_stage: 'CHECK_IN',
      reference_note: 'Advance payment',
      is_reversal: false,
      reverses_payment_id: null,
      received_at: '2026-01-03T10:00:00Z',
    });
    wrap();
    await waitFor(() => expect(screen.getByText('Room Charge - 2 nights @ 2500.00')).toBeInTheDocument());
    fireEvent.change(screen.getAllByLabelText('Amount').pop()!, { target: { value: '3000.00' } });
    fireEvent.click(screen.getByRole('button', { name: /Record Payment/ }));
    await waitFor(() => expect(payments.create).toHaveBeenCalledWith('b1', expect.objectContaining({ amount: 3000, mode: 'CASH', payment_stage: 'CHECK_IN' })));
  });

  it('records a UPI payment at CHECKOUT stage', async () => {
    folio.get.mockResolvedValue(FOLIO);
    payments.create.mockResolvedValue({ id: 'p2', booking_id: 'b1', amount: 1500.00, mode: 'UPI', payment_stage: 'CHECKOUT', reference_note: null, is_reversal: false, reverses_payment_id: null, received_at: '2026-01-03T10:00:00Z' });
    wrap();
    await waitFor(() => expect(screen.getByText('Room Charge - 2 nights @ 2500.00')).toBeInTheDocument());
    fireEvent.change(screen.getAllByLabelText('Amount').pop()!, { target: { value: '1500.00' } });
    fireEvent.change(screen.getAllByLabelText('Mode').pop()!, { target: { value: 'UPI' } });
    fireEvent.change(screen.getAllByLabelText('Stage').pop()!, { target: { value: 'CHECKOUT' } });
    fireEvent.click(screen.getByRole('button', { name: /Record Payment/ }));
    await waitFor(() => expect(payments.create).toHaveBeenCalledWith('b1', expect.objectContaining({ mode: 'UPI', payment_stage: 'CHECKOUT' })));
  });

  it('records a CARD_POS payment at OTHER stage', async () => {
    folio.get.mockResolvedValue(FOLIO);
    payments.create.mockResolvedValue({ id: 'p2', booking_id: 'b1', amount: 1000.00, mode: 'CARD_POS', payment_stage: 'OTHER', reference_note: 'Terminal ref', is_reversal: false, reverses_payment_id: null, received_at: '2026-01-03T10:00:00Z' });
    wrap();
    await waitFor(() => expect(screen.getByText('Room Charge - 2 nights @ 2500.00')).toBeInTheDocument());
    fireEvent.change(screen.getAllByLabelText('Amount').pop()!, { target: { value: '1000.00' } });
    fireEvent.change(screen.getAllByLabelText('Mode').pop()!, { target: { value: 'CARD_POS' } });
    fireEvent.change(screen.getAllByLabelText('Stage').pop()!, { target: { value: 'OTHER' } });
    fireEvent.click(screen.getByRole('button', { name: /Record Payment/ }));
    await waitFor(() => expect(payments.create).toHaveBeenCalledWith('b1', expect.objectContaining({ mode: 'CARD_POS', payment_stage: 'OTHER' })));
  });

  it('rejects invalid payment amount — mutation not called', async () => {
    folio.get.mockResolvedValue(FOLIO);
    wrap();
    await waitFor(() => expect(screen.getAllByLabelText('Amount').length).toBeGreaterThanOrEqual(1));
    fireEvent.change(screen.getAllByLabelText('Amount').pop()!, { target: { value: '-100' } });
    fireEvent.click(screen.getByRole('button', { name: /Record Payment/ }));
    await new Promise((r) => setTimeout(r, 50));
    expect(payments.create).not.toHaveBeenCalled();
  });

  it('handles payment timeout and warns staff', async () => {
    folio.get.mockResolvedValue(FOLIO);
    const timeoutErr: Error & { code?: string } = new Error('Request timed out');
    timeoutErr.code = 'ECONNABORTED';
    payments.create.mockRejectedValue(timeoutErr);
    wrap();
    await waitFor(() => expect(screen.getAllByLabelText('Amount').length).toBeGreaterThanOrEqual(1));
    fireEvent.change(screen.getAllByLabelText('Amount').pop()!, { target: { value: '3000.00' } });
    fireEvent.click(screen.getByRole('button', { name: /Record Payment/ }));
    await waitFor(() => expect(screen.getByText(/outcome may be unknown/)).toBeInTheDocument());
  });
});

describe('folio page — receipts', () => {
  it('displays receipt metadata when available', async () => {
    folio.get.mockResolvedValue(FOLIO);
    bookings.receipt.mockResolvedValue(RECEIPT);
    wrap();
    await waitFor(() => expect(screen.getByText(/SSH-RCP-001/)).toBeInTheDocument());
    expect(screen.getByText(/FINAL/)).toBeInTheDocument();
  });

  it('downloads receipt PDF', async () => {
    const blob = new Blob(['%PDF-1.4 fake'], { type: 'application/pdf' });
    download.mockResolvedValue(blob);
    const createSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click');
    folio.get.mockResolvedValue(FOLIO);
    bookings.receipt.mockResolvedValue(RECEIPT);
    wrap();
    await waitFor(() => expect(screen.getByText(/SSH-RCP-001/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Download PDF/ }));
    await waitFor(() => expect(download).toHaveBeenCalledWith('b1'));
    expect(createSpy).toHaveBeenCalled();
    createSpy.mockRestore();
  });

  it('handles invalid receipt file response', async () => {
    download.mockRejectedValue(new Error('Not a PDF'));
    folio.get.mockResolvedValue(FOLIO);
    bookings.receipt.mockResolvedValue(RECEIPT);
    wrap();
    await waitFor(() => expect(screen.getByText(/SSH-RCP-001/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Download PDF/ }));
    await waitFor(() => expect(screen.getByText(/Request failed/)).toBeInTheDocument());
  });

  it('shows no receipt section when none issued', async () => {
    folio.get.mockResolvedValue(FOLIO);
    bookings.receipt.mockResolvedValue(null);
    wrap();
    await waitFor(() => expect(screen.getByText('Room Charge - 2 nights @ 2500.00')).toBeInTheDocument());
    expect(screen.queryByText(/Final receipt/)).not.toBeInTheDocument();
  });
});
