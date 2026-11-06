export default function AuditPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Audit logs</h1>
      <div className="mt-4 rounded-lg border border-dashed border-stone-300 p-8 text-center">
        <p className="font-medium text-stone-700">Pending feature</p>
        <p className="mt-1 text-sm text-stone-500">The backend audit log is authoritative and is being recorded on every admin mutation. A read API does not exist yet — this page is intentionally not wired to the database. It will be enabled when the audit-log read endpoint ships (later phase).</p>
      </div>
    </div>
  );
}
