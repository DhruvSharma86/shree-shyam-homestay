import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RoomsPage from '@/app/admin/rooms/page';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => '/admin/rooms' }));

const mocks = vi.hoisted(() => ({
  rooms: vi.fn(),
  types: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
}));

vi.mock('@/services/hotel', () => ({
  roomsApi: { list: () => mocks.rooms(), create: (b: unknown) => mocks.create(b), update: (id: string, b: unknown) => mocks.update(id, b) },
  roomTypesApi: { list: () => mocks.types() },
}));

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RoomsPage />
    </QueryClientProvider>,
  );
}

const TYPES = [{ id: 't1', name: 'Deluxe', description: null, maximum_occupancy: 2, amenities: null, is_active: true, display_order: 0 }];

const ROOMS = [
  { id: 'a', room_number: '101', room_type_id: 't1', floor: 1, description: null, maximum_occupancy: 2, operational_status: 'AVAILABLE', is_active: true },
  { id: 'b', room_number: '102', room_type_id: 't1', floor: 1, description: null, maximum_occupancy: 2, operational_status: 'MAINTENANCE', is_active: true },
  { id: 'c', room_number: '103', room_type_id: 't1', floor: 1, description: null, maximum_occupancy: 2, operational_status: 'AVAILABLE', is_active: false },
];

describe('rooms page filters', () => {
  it('Available shows only active AVAILABLE; Maintenance only active MAINTENANCE; Inactive only inactive', async () => {
    mocks.rooms.mockResolvedValue(ROOMS);
    mocks.types.mockResolvedValue(TYPES);
    wrap();
    await waitFor(() => expect(screen.getByRole('button', { name: /Add room/i })).toBeInTheDocument());
    const filterSelect = screen.getAllByRole('combobox')[1];
    // All
    expect(screen.getByText('101')).toBeInTheDocument();
    expect(screen.getByText('102')).toBeInTheDocument();
    expect(screen.getByText('103')).toBeInTheDocument();
    // Available
    fireEvent.change(filterSelect, { target: { value: 'AVAILABLE' } });
    await waitFor(() => expect(screen.getByText('101')).toBeInTheDocument());
    expect(screen.queryByText('102')).not.toBeInTheDocument();
    expect(screen.queryByText('103')).not.toBeInTheDocument();
    // Maintenance
    fireEvent.change(filterSelect, { target: { value: 'MAINTENANCE' } });
    await waitFor(() => expect(screen.getByText('102')).toBeInTheDocument());
    expect(screen.queryByText('101')).not.toBeInTheDocument();
    expect(screen.queryByText('103')).not.toBeInTheDocument();
    // Inactive
    fireEvent.change(filterSelect, { target: { value: 'INACTIVE' } });
    await waitFor(() => expect(screen.getByText('103')).toBeInTheDocument());
    expect(screen.queryByText('101')).not.toBeInTheDocument();
    expect(screen.queryByText('102')).not.toBeInTheDocument();
  });
});
