import { cn } from '@/lib/utils';

export function Button({ className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={cn('inline-flex min-h-11 items-center justify-center rounded-md bg-stone-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50 hover:bg-stone-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-900 focus-visible:ring-offset-2', className)} {...props} />;
}
export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className="w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-900" />;
}
export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('rounded-lg border border-stone-200 bg-white p-4 shadow-sm', className)}>{children}</div>;
}
export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-stone-300 p-8 text-center" role="status">
      <p className="font-medium text-stone-700">{title}</p>
      {hint ? <p className="mt-1 text-sm text-stone-500">{hint}</p> : null}
    </div>
  );
}
export function Field({ label, children, error }: { label: string; children: React.ReactNode; error?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-stone-700">{label}</span>
      {children}
      {error ? <span className="mt-1 block text-xs text-red-600" role="alert">{error}</span> : null}
    </label>
  );
}
export function Spinner() { return <p className="p-4 text-sm text-stone-500" role="status">Loading…</p>; }
export function Err({ message }: { message: string }) {
  return <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">{message}</p>;
}
export function RetryButton({ onRetry, label }: { onRetry: () => void; label: string }) {
  return (
    <Button type="button" onClick={onRetry} aria-label={label}>
      Try again
    </Button>
  );
}
