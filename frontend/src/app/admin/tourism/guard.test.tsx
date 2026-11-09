import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TourismPage from '@/app/admin/tourism/page';
import { useAuthStore } from '@/stores/auth';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock('@/services/auth', () => ({ fetchMe: vi.fn(async () => { throw new Error('401'); }) }));

const mocks = vi.hoisted(() => ({
  packages: vi.fn(async () => []),
  localInfo: vi.fn(async () => []),
}));

vi.mock('@/services/tourism', () => ({
  tourismApi: {
    packages: () => mocks.packages(),
    createPackage: vi.fn(),
    updatePackage: vi.fn(),
    localInfo: () => mocks.localInfo(),
    createLocalInfo: vi.fn(),
    updateLocalInfo: vi.fn(),
  },
}));

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TourismPage />
    </QueryClientProvider>,
  );
}

describe('tourism route guard', () => {
  it('blocks receptionists before content renders', () => {
    useAuthStore.setState({
      me: { user: { username: 'rec1', role: 'RECEPTIONIST', full_name: 'R' } as never, permissions: ['profile.read'] } as never,
      loading: false,
    });
    wrap();
    expect(screen.getByText('Access restricted')).toBeInTheDocument();
  });

  it('allows admins', async () => {
    useAuthStore.setState({
      me: { user: { username: 'admin1', role: 'ADMIN', full_name: 'A' } as never, permissions: ['users.manage'] } as never,
      loading: false,
    });
    wrap();
    expect(screen.getByText('Tourism & local information')).toBeInTheDocument();
  });
});
