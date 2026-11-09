import { RequireStaff } from '@/components/RequireStaff';
import { AdminShell } from '@/components/AdminShell';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <RequireStaff><AdminShell>{children}</AdminShell></RequireStaff>;
}
