import { RequireAdmin } from '@/components/RequireAdmin';
import { AdminShell } from '@/components/AdminShell';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <RequireAdmin><AdminShell>{children}</AdminShell></RequireAdmin>;
}
