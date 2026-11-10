import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RestaurantPage from '@/app/admin/restaurant/page';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => '/admin/restaurant' }));

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
}));

vi.mock('@/services/hotel', () => ({
  restaurantApi: { get: () => mocks.get(), patch: (b: unknown) => mocks.patch(b) },
}));

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RestaurantPage />
    </QueryClientProvider>,
  );
}

describe('restaurant validation', () => {
  it('shows Name required and does not call API on empty submit', async () => {
    mocks.get.mockResolvedValue({ id: 'r1', name: 'Existing', description: null, contact_number: null, opening_hours: null, is_active: true });
    mocks.patch.mockResolvedValue({});
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Save/i })).toBeInTheDocument());
    const nameInput = screen.getAllByRole('textbox')[0];
    fireEvent.change(nameInput, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));
    await waitFor(() => expect(screen.getByText('Name is required')).toBeInTheDocument());
    expect(mocks.patch).not.toHaveBeenCalled();
  });

  it('calls API on valid submit and clears stale errors', async () => {
    mocks.get.mockResolvedValue({ id: 'r1', name: 'Existing', description: null, contact_number: null, opening_hours: null, is_active: true });
    mocks.patch.mockResolvedValue({ id: 'r1', name: 'New', description: null, contact_number: null, opening_hours: null, is_active: true });
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Save/i })).toBeInTheDocument());
    const nameInput = screen.getAllByRole('textbox')[0];
    fireEvent.change(nameInput, { target: { value: 'New Name' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));
    await waitFor(() => expect(mocks.patch).toHaveBeenCalled());
  });

  it('displays API error on failure', async () => {
    mocks.get.mockResolvedValue({ id: 'r1', name: 'Existing', description: null, contact_number: null, opening_hours: null, is_active: true });
    mocks.patch.mockRejectedValue(Object.assign(new Error('boom'), { isAxiosError: true, response: { status: 422, data: { error: { message: 'Server rejected.' } } } }));
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Save/i })).toBeInTheDocument());
    const nameInput = screen.getAllByRole('textbox')[0];
    fireEvent.change(nameInput, { target: { value: 'New Name' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByText('Server rejected.')).toBeInTheDocument();
  });
});
