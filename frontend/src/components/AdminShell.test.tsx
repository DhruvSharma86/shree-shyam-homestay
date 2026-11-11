import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminShell } from '@/components/AdminShell';
import { useAuthStore } from '@/stores/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/admin/bookings',
}));

function setRole(username: string, role: 'ADMIN' | 'RECEPTIONIST', permissions: string[]) {
  useAuthStore.setState({
    me: { user: { username, role, full_name: 'U' } as never, permissions } as never,
    loading: false,
  });
}

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AdminShell><p>content</p></AdminShell>
    </QueryClientProvider>,
  );
}

describe('AdminShell navigation', () => {
  it('shows full navigation to ADMIN', () => {
    setRole('admin1', 'ADMIN', ['users.manage']);
    wrap();
    // Staff navigation
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Guests')).toBeInTheDocument();
    expect(screen.getByText('Bookings')).toBeInTheDocument();
    // Admin-only navigation
    expect(screen.getByText('Hotel')).toBeInTheDocument();
    expect(screen.getByText('Room types')).toBeInTheDocument();
    expect(screen.getByText('Rooms')).toBeInTheDocument();
    expect(screen.getByText('Room rates')).toBeInTheDocument();
    expect(screen.getByText('Tax settings')).toBeInTheDocument();
    expect(screen.getByText('Restaurant')).toBeInTheDocument();
    expect(screen.getByText('Menu')).toBeInTheDocument();
    expect(screen.getByText('Cab providers')).toBeInTheDocument();
    expect(screen.getByText('Tourism')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Audit logs')).toBeInTheDocument();
  });

  it('shows only staff navigation to RECEPTIONIST', () => {
    setRole('rec1', 'RECEPTIONIST', ['bookings.read', 'bookings.write', 'guests.read', 'guests.write']);
    wrap();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Guests')).toBeInTheDocument();
    expect(screen.getByText('Bookings')).toBeInTheDocument();
    expect(screen.queryByText('Hotel')).not.toBeInTheDocument();
    expect(screen.queryByText('Users')).not.toBeInTheDocument();
    expect(screen.queryByText('Audit logs')).not.toBeInTheDocument();
  });

  it('has data-testid attributes on nav links', () => {
    setRole('admin1', 'ADMIN', ['users.manage']);
    wrap();
    expect(screen.getByTestId('nav-dashboard')).toBeInTheDocument();
    expect(screen.getByTestId('nav-guests')).toBeInTheDocument();
    expect(screen.getByTestId('nav-bookings')).toBeInTheDocument();
    expect(screen.getByTestId('nav-tourism')).toBeInTheDocument();
  });
});
