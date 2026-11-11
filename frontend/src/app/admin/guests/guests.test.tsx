import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import GuestsPage from '@/app/admin/guests/page';
import { useAuthStore } from '@/stores/auth';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => '/admin/guests' }));

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
}));

vi.mock('@/services/guests', () => ({
  guestsApi: {
    list: (...a: unknown[]) => mocks.list(...a),
    create: (b: unknown) => mocks.create(b),
    get: vi.fn(),
    update: vi.fn(),
    deactivate: vi.fn(),
  },
}));

const GUEST = { id: 'g1', full_name: 'Alice Guest', phone: '+919000000000' };

function setRole(username: string, role: 'ADMIN' | 'RECEPTIONIST', permissions: string[]) {
  useAuthStore.setState({
    me: { user: { username, role, full_name: 'U' } as never, permissions } as never,
    loading: false,
  });
}

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><GuestsPage /></QueryClientProvider>,
  );
}

describe('guests page', () => {
  it('loads and renders guest list', async () => {
    mocks.list.mockResolvedValue({ items: [{ id: 'g1', full_name: 'Alice Guest', phone: '+919000000000', email: null, address: null, notes: null, is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }], total: 1, page: 1, page_size: 20 });
    wrap();
    await waitFor(() => expect(screen.getByText('Alice Guest')).toBeInTheDocument());
    expect(screen.getByText('+919000000000')).toBeInTheDocument();
  });

  it('shows empty state', async () => {
    mocks.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    wrap();
    await waitFor(() => expect(screen.getByText('No guests found')).toBeInTheDocument());
  });

  it('shows error state', async () => {
    mocks.list.mockRejectedValue(new Error('boom'));
    wrap();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('validation: empty name shows error and does not call API', async () => {
    mocks.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mocks.create.mockResolvedValue({});
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Register/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Register/i }));
    await waitFor(() => expect(screen.getByText('Name is required')).toBeInTheDocument());
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('registers a guest with correct payload and refreshes list', async () => {
    mocks.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mocks.create.mockResolvedValue({ id: 'g2', full_name: 'Bob', phone: '+919111111111', email: null, address: null, notes: null, is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' });
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Register/i })).toBeInTheDocument());
    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0], { target: { value: 'Bob' } });
    fireEvent.change(inputs[1], { target: { value: '+919111111111' } });
    fireEvent.click(screen.getByRole('button', { name: /Register/i }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ full_name: 'Bob', phone: '+919111111111' })));
    await waitFor(() => expect(screen.getByText('Guest registered.')).toBeInTheDocument());
  });

  it('shows API error on registration failure', async () => {
    mocks.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mocks.create.mockRejectedValue(Object.assign(new Error('boom'), { isAxiosError: true, response: { status: 409, data: { error: { message: 'A guest with this name and phone already exists.' } } } }));
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Register/i })).toBeInTheDocument());
    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0], { target: { value: 'Bob' } });
    fireEvent.change(inputs[1], { target: { value: '+919111111111' } });
    fireEvent.click(screen.getByRole('button', { name: /Register/i }));
    await waitFor(() => expect(screen.getByText('A guest with this name and phone already exists.')).toBeInTheDocument());
  });

  it('search submits and shows no-results', async () => {
    mocks.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Search/i })).toBeInTheDocument());
    const searchInput = screen.getAllByRole('textbox').slice(-1)[0];
    fireEvent.change(searchInput, { target: { value: 'zzz' } });
    fireEvent.click(screen.getByRole('button', { name: /Search/i }));
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith('zzz', 1, 20));
  });

  it('receptionist can access guest page', async () => {
    mocks.list.mockResolvedValue({ items: [GUEST], total: 1, page: 1, page_size: 20 });
    setRole('rec1', 'RECEPTIONIST', ['guests.read', 'guests.write']);
    wrap();
    await waitFor(() => expect(screen.getByText('Alice Guest')).toBeInTheDocument());
    expect(screen.getByText('+919000000000')).toBeInTheDocument();
  });
});
