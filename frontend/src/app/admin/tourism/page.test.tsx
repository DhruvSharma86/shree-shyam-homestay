import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TourismPage from '@/app/admin/tourism/page';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const mocks = vi.hoisted(() => ({
  packages: vi.fn(),
  createPackage: vi.fn(),
  updatePackage: vi.fn(),
  localInfo: vi.fn(),
  createLocalInfo: vi.fn(),
  updateLocalInfo: vi.fn(),
}));

vi.mock('@/services/tourism', () => ({
  tourismApi: {
    packages: () => mocks.packages(),
    createPackage: (b: unknown) => mocks.createPackage(b),
    updatePackage: (id: string, b: unknown) => mocks.updatePackage(id, b),
    localInfo: () => mocks.localInfo(),
    createLocalInfo: (b: unknown) => mocks.createLocalInfo(b),
    updateLocalInfo: (id: string, b: unknown) => mocks.updateLocalInfo(id, b),
  },
  bookingsApi: {},
  downloadStaffReceipt: vi.fn(),
}));

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TourismPage />
    </QueryClientProvider>,
  );
}

describe('tourism admin page', () => {
  it('renders existing packages and local info', async () => {
    mocks.packages.mockResolvedValue([
      { id: '1', name: 'Fort Walk', description: null, duration: '3 hours', price: '800.00', image_url: null, contact_number: null, is_active: true, display_order: 0 },
    ]);
    mocks.localInfo.mockResolvedValue([
      { id: '1', title: 'Heritage Park', description: null, location: 'Lake Road', contact_number: null, image_url: null, is_active: true, display_order: 0 },
    ]);
    wrap();
    await waitFor(() => expect(screen.getByText('Fort Walk')).toBeInTheDocument());
    expect(screen.getByText('Heritage Park')).toBeInTheDocument();
  });

  it('creates a tour package', async () => {
    mocks.packages.mockResolvedValue([]);
    mocks.localInfo.mockResolvedValue([]);
    mocks.createPackage.mockResolvedValue({ id: '2', name: 'Lake Cruise', is_active: true });
    wrap();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Lake Cruise' } });
    const submits = screen.getAllByText('Add');
    fireEvent.click(submits[0]);
    await waitFor(() => expect(mocks.createPackage).toHaveBeenCalled());
    expect(mocks.createPackage.mock.calls[0][0]).toMatchObject({ name: 'Lake Cruise' });
  });
});
