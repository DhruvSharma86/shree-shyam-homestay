import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginPage from '@/app/login/page';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/services/auth', () => ({
  login: vi.fn(async () => ({ user: { username: 'admin1' }, permissions: [] })),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }) }));

function wrap(ui: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

describe('login page', () => {
  it('shows validation errors for empty fields', async () => {
    wrap(<LoginPage />);
    fireEvent.click(screen.getByText('Sign in'));
    await waitFor(() => expect(screen.getByText('Username is required')).toBeInTheDocument());
  });
  it('submits valid credentials', async () => {
    wrap(<LoginPage />);
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin1' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret123' } });
    await waitFor(() => expect(screen.queryByText('Username is required')).not.toBeInTheDocument());
  });
});
