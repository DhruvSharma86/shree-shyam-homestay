import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { RequireAdmin } from '@/components/RequireAdmin';
import { useAuthStore } from '@/stores/auth';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock('@/services/auth', () => ({ fetchMe: vi.fn(async () => { throw new Error('401'); }) }));

describe('RequireAdmin', () => {
  it('shows loading then redirects when unauthenticated', async () => {
    useAuthStore.setState({ me: null, loading: false });
    render(<RequireAdmin><p>secret</p></RequireAdmin>);
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });
  it('blocks receptionists', () => {
    useAuthStore.setState({
      me: { user: { username: 'rec1', role: 'RECEPTIONIST', full_name: 'R' } as never, permissions: ['profile.read'] },
      loading: false,
    });
    render(<RequireAdmin><p>secret</p></RequireAdmin>);
    expect(screen.getByText('Access restricted')).toBeInTheDocument();
  });
  it('allows admins', () => {
    useAuthStore.setState({
      me: { user: { username: 'admin1', role: 'ADMIN', full_name: 'A' } as never, permissions: ['users.manage'] },
      loading: false,
    });
    render(<RequireAdmin><p>secret</p></RequireAdmin>);
    expect(screen.getByText('secret')).toBeInTheDocument();
  });

  it('blocks receptionists after ADMIN session', async () => {
    useAuthStore.setState({
      me: { user: { username: 'admin1', role: 'ADMIN', full_name: 'A' } as never, permissions: ['users.manage'] },
      loading: false,
    });
    render(<RequireAdmin><p>secret</p></RequireAdmin>);
    expect(screen.getByText('secret')).toBeInTheDocument();

    useAuthStore.setState({
      me: { user: { username: 'rec1', role: 'RECEPTIONIST', full_name: 'R' } as never, permissions: ['profile.read'] },
      loading: false,
    });
    await waitFor(() => expect(screen.getByText('Access restricted')).toBeInTheDocument());
  });
});
