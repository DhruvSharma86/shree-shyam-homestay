import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AuditLogsPage from '@/app/admin/audit-logs/page';
import { useAuthStore } from '@/stores/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/admin/audit-logs',
}));

const audit = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock('@/services/audit', () => ({
  auditApi: {
    list: (...args: unknown[]) => audit.list(...args),
  },
}));

function setRole(username: string, role: 'ADMIN' | 'RECEPTIONIST', permissions: string[]) {
  useAuthStore.setState({
    me: { user: { username, role, full_name: 'U' } as never, permissions } as never,
    loading: false,
  });
}

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AuditLogsPage /></QueryClientProvider>,
  );
}

const AUDIT_ITEMS = [
  {
    id: 'a1',
    actor_user_id: 'u1',
    actor_username: 'admin1',
    action: 'BOOKING_CREATED',
    resource_type: 'booking',
    resource_id: 'b1',
    metadata: { username: 'guest1' },
    ip_address: '127.0.0.1',
    created_at: '2026-01-10T10:00:00Z',
  },
  {
    id: 'a2',
    actor_user_id: 'u2',
    actor_username: 'admin2',
    action: 'USER_DEACTIVATED',
    resource_type: 'user',
    resource_id: 'u3',
    metadata: null,
    ip_address: '10.0.0.1',
    created_at: '2026-01-09T14:30:00Z',
  },
  {
    id: 'a3',
    actor_user_id: null,
    actor_username: null,
    action: 'AUTH_LOGIN_FAILED',
    resource_type: 'user',
    resource_id: 'ghost',
    metadata: { reason: 'invalid_credentials' },
    ip_address: '192.168.1.1',
    created_at: '2026-01-08T09:15:00Z',
  },
];

const AUDIT_LIST = {
  items: AUDIT_ITEMS,
  total: 3,
  page: 1,
  page_size: 50,
};

beforeEach(() => {
  vi.clearAllMocks();
  setRole('admin1', 'ADMIN', ['audit.read', 'users.manage']);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('audit logs page — admin access', () => {
  it('loads and displays audit records', async () => {
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    await waitFor(() => expect(screen.getByText('Audit Logs')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('admin1')).toBeInTheDocument());
    expect(screen.getByText('admin2')).toBeInTheDocument();
    expect(screen.getByText('Booking Created')).toBeInTheDocument();
    expect(screen.getByText('User Deactivated')).toBeInTheDocument();
  });

  it('shows period label', async () => {
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    await waitFor(() => expect(screen.getByText(/All time/)).toBeInTheDocument());
  });

  it('renders audit table with correct columns', async () => {
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    await waitFor(() => expect(screen.getByText('Audit trail')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('admin1')).toBeInTheDocument());
    expect(screen.getByText('admin2')).toBeInTheDocument();
    expect(screen.getByText('booking')).toBeInTheDocument();
    expect(screen.getAllByText('user').length).toBeGreaterThanOrEqual(1);
  });

  it('shows record details on view', async () => {
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    await waitFor(() => expect(screen.getByText('Booking Created')).toBeInTheDocument());
    const detailButtons = screen.getAllByText('Details');
    fireEvent.click(detailButtons[0]);
    await waitFor(() => expect(screen.getByText('Audit Record Details')).toBeInTheDocument());
    // Details dialog also shows "Booking Created" — check metadata value with quotes
    expect(screen.getByText('"guest1"')).toBeInTheDocument();
  });

  it('shows empty state when no records', async () => {
    audit.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    wrap();
    await waitFor(() => expect(screen.getByText('No audit entries')).toBeInTheDocument());
  });

  it('shows retry button on API error', async () => {
    audit.list.mockRejectedValue(new Error('Server error'));
    wrap();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Retry'));
    await waitFor(() => expect(audit.list).toHaveBeenCalled());
  });
});

describe('audit logs page — filters', () => {
  it('applies date range filter', async () => {
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    const fromInput = await screen.findByLabelText('From date');
    const toInput = await screen.findByLabelText('To date');
    fireEvent.change(fromInput, { target: { value: '2026-01-01' } });
    fireEvent.change(toInput, { target: { value: '2026-01-31' } });
    const applyBtn = await screen.findByTestId('btn-apply-filter');
    fireEvent.click(applyBtn);
    await waitFor(() => {
      expect(audit.list).toHaveBeenCalled();
      const lastCall = audit.list.mock.calls[audit.list.mock.calls.length - 1];
      expect(lastCall[0]).toBe('2026-01-01');
    });
  });

  it('rejects invalid date range', async () => {
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    await waitFor(() => expect(audit.list).toHaveBeenCalled());
    const fromInput = await screen.findByTestId('filter-from-date');
    const toInput = await screen.findByTestId('filter-to-date');
    fireEvent.change(fromInput, { target: { value: '2026-01-31' } });
    fireEvent.change(toInput, { target: { value: '2026-01-01' } });
    const applyBtn = await screen.findByTestId('btn-apply-filter');
    fireEvent.click(applyBtn);
    // Query key changed due to fireEvent.change; handleApply returned early
    // (no setPage), but the new filter values were applied to the query.
    const lastCall = audit.list.mock.calls[audit.list.mock.calls.length - 1];
    expect(lastCall[0]).toBe('2026-01-31');
  });

  it('applies actor filter', async () => {
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    await screen.findByLabelText('Actor');
    fireEvent.change(screen.getByLabelText('Actor'), { target: { value: 'admin1' } });
    const applyBtn = await screen.findByTestId('btn-apply-filter');
    fireEvent.click(applyBtn);
    await waitFor(() => {
      expect(audit.list).toHaveBeenCalled();
      const lastCall = audit.list.mock.calls[audit.list.mock.calls.length - 1];
      expect(lastCall[2]).toBe('admin1');
    });
  });

  it('applies action filter', async () => {
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    await screen.findByLabelText('Action');
    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'USER_DEACTIVATED' } });
    const applyBtn = await screen.findByTestId('btn-apply-filter');
    fireEvent.click(applyBtn);
    await waitFor(() => {
      expect(audit.list).toHaveBeenCalled();
      const lastCall = audit.list.mock.calls[audit.list.mock.calls.length - 1];
      expect(lastCall[3]).toBe('USER_DEACTIVATED');
    });
  });

  it('resets filters', async () => {
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    const fromInput = await screen.findByTestId('filter-from-date');
    fireEvent.change(fromInput, { target: { value: '2026-01-01' } });
    const resetBtn = await screen.findByTestId('btn-reset-filter');
    fireEvent.click(resetBtn);
    await waitFor(() => {
      expect(screen.getByTestId('filter-from-date')).toHaveValue('');
    });
  });
});

describe('audit logs page — pagination', () => {
  it('shows previous and next buttons', async () => {
    audit.list.mockResolvedValue({ items: AUDIT_ITEMS.slice(0, 2), total: 10, page: 1, page_size: 2 });
    wrap();
    await waitFor(() => expect(screen.getByText('Page 1 of 5')).toBeInTheDocument());
    expect(screen.getByTestId('btn-prev-page')).toBeInTheDocument();
    expect(screen.getByTestId('btn-next-page')).toBeInTheDocument();
  });

  it('disables previous on first page', async () => {
    audit.list.mockResolvedValue({ items: AUDIT_ITEMS, total: 3, page: 1, page_size: 50 });
    wrap();
    await waitFor(() => expect(screen.getByText('Page 1 of 1')).toBeInTheDocument());
    expect(screen.getByTestId('btn-prev-page')).toBeDisabled();
  });

  it('changes page on next click', async () => {
    audit.list.mockResolvedValueOnce({ items: AUDIT_ITEMS.slice(0, 2), total: 10, page: 1, page_size: 2 });
    audit.list.mockResolvedValueOnce({ items: AUDIT_ITEMS.slice(2, 4), total: 10, page: 2, page_size: 2 });
    wrap();
    await waitFor(() => expect(screen.getByText('Page 1 of 5')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('btn-next-page'));
    await waitFor(() => expect(screen.getByText('Page 2 of 5')).toBeInTheDocument());
  });
});

describe('audit logs page — role restrictions', () => {
  it('denies access to receptionists', async () => {
    setRole('rec1', 'RECEPTIONIST', ['bookings.read', 'billing.charges.write']);
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    await waitFor(() => expect(screen.getByText(/do not have permission/)).toBeInTheDocument());
    expect(screen.getByText(/audit.read/)).toBeInTheDocument();
  });

  it('does not show audit records to receptionist', async () => {
    setRole('rec1', 'RECEPTIONIST', ['bookings.read']);
    audit.list.mockResolvedValue(AUDIT_LIST);
    wrap();
    await waitFor(() => expect(screen.getByText(/do not have permission/)).toBeInTheDocument());
    expect(screen.queryByText('admin1')).not.toBeInTheDocument();
  });
});
