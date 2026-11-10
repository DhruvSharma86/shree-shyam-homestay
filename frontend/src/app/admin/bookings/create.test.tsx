import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import BookingsPage from '@/app/admin/bookings/page';
import { useAuthStore } from '@/stores/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/admin/bookings',
}));

const bookings = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  create: vi.fn(),
  availability: vi.fn(),
}));
const guests = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
}));
const hotel = vi.hoisted(() => ({
  rooms: vi.fn(),
  types: vi.fn(),
}));

vi.mock('@/services/tourism', () => ({
  bookingsApi: {
    list: (...a: unknown[]) => bookings.list(...a),
    get: (id: string) => bookings.get(id),
    create: (b: unknown) => bookings.create(b),
    availability: (ci: string, co: string) => bookings.availability(ci, co),
    recordCheckInPayment: vi.fn(),
    checkIn: vi.fn(),
    rotatePortal: vi.fn(),
    revokePortal: vi.fn(),
  },
  tourismApi: {},
  downloadStaffReceipt: vi.fn(),
}));
vi.mock('@/services/guests', () => ({
  guestsApi: {
    list: (...a: unknown[]) => guests.list(...a),
    create: (b: unknown) => guests.create(b),
    get: vi.fn(),
    update: vi.fn(),
    deactivate: vi.fn(),
  },
}));
vi.mock('@/services/hotel', () => ({
  roomsApi: { list: (...a: unknown[]) => hotel.rooms(...a) },
  roomTypesApi: { list: (...a: unknown[]) => hotel.types(...a) },
}));

function setRole(username: string, role: 'ADMIN' | 'RECEPTIONIST', permissions: string[]) {
  useAuthStore.setState({
    me: { user: { username, role, full_name: 'U' } as never, permissions } as never,
    loading: false,
  });
}

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><BookingsPage /></QueryClientProvider>,
  );
}

const GUEST = { id: 'g1', full_name: 'Alice Guest', phone: '+919000000000' };
const ROOMS = [
  { id: 'r1', room_number: '101', room_type_id: 't1', maximum_occupancy: 2, operational_status: 'AVAILABLE', is_active: true },
  { id: 'r2', room_number: '102', room_type_id: 't1', maximum_occupancy: 3, operational_status: 'AVAILABLE', is_active: true },
];
const TYPES = [{ id: 't1', name: 'Deluxe', maximum_occupancy: 2 }];

const newBooking = {
  id: 'b2',
  booking_ref: 'SSH-BBB',
  status: 'CONFIRMED',
  guest_id: 'g1',
  room_id: 'r1',
  room_type_id: 't1',
  source: 'PHONE',
  check_in_date: '2026-11-12',
  check_out_date: '2026-11-14',
  nights: 2,
  number_of_guests: 2,
  notes: null,
  night_rate_snapshot: '2500.00',
  rate_id: null,
  room_subtotal: '5000.00',
  tax_type_snapshot: 'NONE',
  tax_rate_snapshot: null,
  tax_pricing_mode_snapshot: 'EXCLUSIVE',
  total_amount: '5000.00',
  cancelled_at: null,
  cancellation_reason: null,
};

beforeEach(() => {
  vi.resetAllMocks();
  setRole('admin1', 'ADMIN', ['bookings.write', 'bookings.read', 'guests.write', 'guests.read']);
  bookings.list.mockResolvedValue({
    items: [{ id: 'b1', booking_ref: 'SSH-AAA', status: 'CONFIRMED', check_in_date: '2026-11-10', check_out_date: '2026-11-11', nights: 1 }],
    total: 1,
    page: 1,
    page_size: 50,
  });
  hotel.rooms.mockResolvedValue(ROOMS);
  hotel.types.mockResolvedValue(TYPES);
});

function openCreate() {
  fireEvent.click(screen.getByText('Create booking'));
}

async function selectGuest() {
  const searchInput = screen.getByPlaceholderText('Search by name/phone\u2026');
  fireEvent.change(searchInput, { target: { value: 'Alice' } });
  fireEvent.click(screen.getByRole('button', { name: /Search/i }));
  await waitFor(() => expect(screen.getByRole('button', { name: /Alice Guest/ })).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: /Alice Guest/ }));
}

describe('booking creation', () => {
  it('searches existing guests and selects one', async () => {
    guests.list.mockResolvedValue({ items: [GUEST], total: 1, page: 1, page_size: 20 });
    wrap();
    openCreate();
    const searchInput = screen.getByPlaceholderText('Search by name/phone\u2026');
    fireEvent.change(searchInput, { target: { value: 'Alice' } });
    fireEvent.click(screen.getByRole('button', { name: /Search/i }));
    await waitFor(() => expect(guests.list).toHaveBeenCalledWith('Alice', 1, 20));
    await waitFor(() => expect(screen.getByRole('button', { name: /Alice Guest/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Alice Guest/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /change/ })).toBeInTheDocument());
  });

  it('shows no-guests hint when search finds nothing', async () => {
    guests.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    wrap();
    openCreate();
    fireEvent.click(screen.getByRole('button', { name: /Search/i }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /Alice Guest/ })).not.toBeInTheDocument());
  });

  it('rejects check-out before check-in', async () => {
    guests.list.mockResolvedValue({ items: [GUEST], total: 1, page: 1, page_size: 20 });
    wrap();
    openCreate();
    await selectGuest();
    const ci = screen.getByLabelText('Check-in date');
    const co = screen.getByLabelText('Check-out date');
    fireEvent.change(ci, { target: { value: '2026-11-14' } });
    fireEvent.change(co, { target: { value: '2026-11-12' } });
    fireEvent.click(screen.getByRole('button', { name: /Check availability/i }));
    await waitFor(() => expect(screen.getByText('Check-out must be after check-in.')).toBeInTheDocument());
  });

  it('checks availability with correct dates and lists available rooms', async () => {
    guests.list.mockResolvedValue({ items: [GUEST], total: 1, page: 1, page_size: 20 });
    bookings.availability.mockResolvedValue([
      { room_id: 'r1', available: true, check_in_date: '2026-11-12', check_out_date: '2026-11-14' },
      { room_id: 'r2', available: false, check_in_date: '2026-11-12', check_out_date: '2026-11-14' },
    ]);
    wrap();
    openCreate();
    selectGuest();
    const ci = screen.getByLabelText('Check-in date');
    const co = screen.getByLabelText('Check-out date');
    fireEvent.change(ci, { target: { value: '2026-11-12' } });
    fireEvent.change(co, { target: { value: '2026-11-14' } });
    fireEvent.click(screen.getByRole('button', { name: /Check availability/i }));
    await waitFor(() => expect(bookings.availability).toHaveBeenCalledWith('2026-11-12', '2026-11-14'));
    await waitFor(() => expect(screen.getByText(/Room 101/)).toBeInTheDocument());
    expect(screen.queryByText(/Room 102/)).not.toBeInTheDocument();
  });

  it('creates a booking with correct payload', async () => {
    guests.list.mockResolvedValue({ items: [GUEST], total: 1, page: 1, page_size: 20 });
    bookings.availability.mockResolvedValue([
      { room_id: 'r1', available: true, check_in_date: '2026-11-12', check_out_date: '2026-11-14' },
    ]);
    bookings.create.mockResolvedValue(newBooking);
    bookings.get.mockResolvedValue(newBooking);
    wrap();
    openCreate();
    selectGuest();
    const ci = screen.getByLabelText('Check-in date');
    const co = screen.getByLabelText('Check-out date');
    fireEvent.change(ci, { target: { value: '2026-11-12' } });
    fireEvent.change(co, { target: { value: '2026-11-14' } });
    fireEvent.click(screen.getByRole('button', { name: /Check availability/i }));
    await waitFor(() => expect(screen.getByText(/Room 101/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Room 101/));
    const guestsInput = screen.getByLabelText('Number of guests');
    fireEvent.change(guestsInput, { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: /Create booking/ }));
    await waitFor(() => expect(bookings.create).toHaveBeenCalledWith(
      expect.objectContaining({ guest_id: 'g1', room_id: 'r1', source: 'PHONE', number_of_guests: 2 }),
    ));
    await waitFor(() => expect(screen.getByText(/SSH-BBB/)).toBeInTheDocument());
  });

  it('rejects over-capacity booking and shows backend error', async () => {
    guests.list.mockResolvedValue({ items: [GUEST], total: 1, page: 1, page_size: 20 });
    bookings.availability.mockResolvedValue([
      { room_id: 'r1', available: true, check_in_date: '2026-11-12', check_out_date: '2026-11-14' },
    ]);
    bookings.create.mockRejectedValue(Object.assign(new Error('boom'), {
      isAxiosError: true,
      response: { status: 422, data: { error: { message: 'Room 101 accommodates at most 2 guest(s); requested 4.' } } },
    }));
    wrap();
    openCreate();
    selectGuest();
    const ci = screen.getByLabelText('Check-in date');
    const co = screen.getByLabelText('Check-out date');
    fireEvent.change(ci, { target: { value: '2026-11-12' } });
    fireEvent.change(co, { target: { value: '2026-11-14' } });
    fireEvent.click(screen.getByRole('button', { name: /Check availability/i }));
    await waitFor(() => expect(screen.getByText('Room 101 (Deluxe) \u2014 max 2 guests')).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Room 101/));
    const guestsInput = screen.getByLabelText('Number of guests');
    fireEvent.change(guestsInput, { target: { value: '4' } });
    fireEvent.click(screen.getByRole('button', { name: /Create booking/ }));
    await waitFor(() => expect(screen.getAllByText(/accommodates at most 2 guest\(s\); requested 4/).length).toBeGreaterThan(0));
  });
});
