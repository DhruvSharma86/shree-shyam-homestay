import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RequireStaff } from '@/components/RequireStaff';
import { useAuthStore } from '@/stores/auth';

const replace = vi.fn();

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }));
vi.mock('@/services/auth', () => ({ fetchMe: vi.fn(async () => { throw new Error('401'); }) }));

describe('RequireStaff', () => {
  it('renders children for receptionists', () => {
    useAuthStore.setState({
      me: {
        user: { username: 'rec1', role: 'RECEPTIONIST', full_name: 'R' } as never,
        permissions: ['bookings.read'],
      } as never,
      loading: false,
    });
    render(<RequireStaff><p>booking ops</p></RequireStaff>);
    expect(screen.getByText('booking ops')).toBeInTheDocument();
  });

  it('renders children for admins', () => {
    useAuthStore.setState({
      me: {
        user: { username: 'admin1', role: 'ADMIN', full_name: 'A' } as never,
        permissions: ['users.manage'],
      } as never,
      loading: false,
    });
    render(<RequireStaff><p>booking ops</p></RequireStaff>);
    expect(screen.getByText('booking ops')).toBeInTheDocument();
  });

  it('shows loading and redirects when unauthenticated', () => {
    useAuthStore.setState({ me: null, loading: false });
    render(<RequireStaff><p>booking ops</p></RequireStaff>);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('booking ops')).not.toBeInTheDocument();
  });
});
