import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RatesPage from '@/app/admin/room-rates/page';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => '/admin/room-rates' }));

const mocks = vi.hoisted(() => ({
  rates: vi.fn(),
  types: vi.fn(),
  create: vi.fn(),
}));

vi.mock('@/services/hotel', () => ({
  ratesApi: { list: () => mocks.rates(), create: (b: unknown) => mocks.create(b) },
  roomTypesApi: { list: () => mocks.types() },
}));

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RatesPage />
    </QueryClientProvider>,
  );
}

const TYPES = [{ id: 't1', name: 'Deluxe', description: null, maximum_occupancy: 2, amenities: null, is_active: true, display_order: 0 }];

describe('room rates error state', () => {
  it('clears a stale error after a successful creation', async () => {
    mocks.rates.mockResolvedValue([]);
    mocks.types.mockResolvedValue(TYPES);
    mocks.create
      .mockRejectedValueOnce(Object.assign(new Error('overlap'), { isAxiosError: true, response: { data: { error: { message: 'Rate period overlaps an existing rate.' } } } }))
      .mockResolvedValueOnce({ id: 'r1', room_type_id: 't1', nightly_rate: '2500.00', valid_from: '2026-11-10', valid_until: null, is_active: true });
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Add rate/i })).toBeInTheDocument());
    const typeSelect = screen.getAllByRole('combobox')[0];
    const inputs = document.querySelectorAll('input');
    const rateInput = inputs[0] as HTMLInputElement;
    const fromInput = inputs[1] as HTMLInputElement;
    // first attempt fails
    fireEvent.change(typeSelect, { target: { value: 't1' } });
    fireEvent.change(rateInput, { target: { value: '2500.00' } });
    fireEvent.change(fromInput, { target: { value: '2026-11-10' } });
    fireEvent.click(screen.getByRole('button', { name: /Add rate/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    // second attempt succeeds -> error cleared
    fireEvent.change(fromInput, { target: { value: '2026-12-10' } });
    fireEvent.click(screen.getByRole('button', { name: /Add rate/i }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
});
