'use client';
import { useState, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { folioApi, paymentsApi, bookingsApi } from '@/services/tourism';
import { apiErrorMessage, mutationErrorMessage } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { Button, Card, Empty, Err, Field, Input, Spinner } from '@/components/ui/primitives';

const folioSchema = z.object({
  description: z.string().min(1, 'Description is required').max(255),
  quantity: z.coerce.number().min(0.01, 'Quantity must be greater than 0'),
  unit_amount: z.coerce.number().min(0, 'Unit amount must be 0 or greater'),
});

const discountSchema = z.object({
  amount: z.coerce.number().min(0.01, 'Amount must be greater than 0'),
  reason: z.string().min(1, 'Reason is required').max(1000),
});

const reversalConfirmSchema = z.object({
  reason: z.string().min(1, 'Reason is required').max(1000),
});

const paymentSchema = z.object({
  amount: z.coerce.number().min(0.01, 'Amount must be greater than 0'),
  mode: z.enum(['CASH', 'UPI', 'CARD_POS']),
  payment_stage: z.enum(['ADVANCE', 'CHECK_IN', 'CHECKOUT', 'OTHER']),
  reference_note: z.string().optional(),
  overpayment_reason: z.string().optional(),
});

export default function FolioPage({ booking_id }: { booking_id: string }) {
  const qc = useQueryClient();
  const { me } = useAuthStore();
  const permissions = me?.permissions ?? [];
  const canWriteCharges = permissions.includes('billing.charges.write');
  const canWriteDiscounts = permissions.includes('billing.discounts.write');
  const canReadReceipts = permissions.includes('billing.receipts.read');

  const folio = useQuery({ queryKey: ['folio', booking_id], queryFn: () => folioApi.get(booking_id) });
  const payments = useQuery({ queryKey: ['payments', booking_id], queryFn: () => paymentsApi.list(booking_id) });
  const receipt = useQuery({ queryKey: ['receipt', booking_id], queryFn: () => bookingsApi.receipt(booking_id), enabled: canReadReceipts });

  const createCharge = useMutation({
    mutationFn: (b: unknown) => folioApi.createCharge(booking_id, b),
    retry: false,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['folio', booking_id] }); },
    onError: (e) => setErr(mutationErrorMessage(e)),
  });
  const createDiscount = useMutation({
    mutationFn: (b: unknown) => folioApi.createDiscount(booking_id, b),
    retry: false,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['folio', booking_id] }); },
    onError: (e) => setErr(mutationErrorMessage(e)),
  });
  const createReversal = useMutation({
    mutationFn: (b: unknown) => folioApi.createReversal(booking_id, b),
    retry: false,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['folio', booking_id] }); },
    onError: (e) => setErr(mutationErrorMessage(e)),
  });
  const createPayment = useMutation({
    mutationFn: (b: unknown) => paymentsApi.create(booking_id, b),
    retry: false,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folio', booking_id] });
      qc.invalidateQueries({ queryKey: ['payments', booking_id] });
    },
    onError: (e) => setErr(mutationErrorMessage(e)),
  });

  const [err, setErr] = useState('');
  const [showChargeForm, setShowChargeForm] = useState(false);
  const [showDiscountForm, setShowDiscountForm] = useState(false);
  const [confirmReversal, setConfirmReversal] = useState<string | null>(null);
  const [receiptDownloadErr, setReceiptDownloadErr] = useState('');
  const reversalEntryIdRef = useRef<HTMLInputElement>(null);

  const { register: cRegister, handleSubmit: cHandleSubmit, formState: { errors: cErrors } } = useForm({ resolver: zodResolver(folioSchema) });
  const { register: dRegister, handleSubmit: dHandleSubmit, formState: { errors: dErrors } } = useForm({ resolver: zodResolver(discountSchema) });
  const { register: rcRegister, handleSubmit: rcHandleSubmit, formState: { errors: rcErrors } } = useForm({ resolver: zodResolver(reversalConfirmSchema) });
  const { register: pRegister, handleSubmit: pHandleSubmit, formState: { errors: pErrors } } = useForm({ resolver: zodResolver(paymentSchema), defaultValues: { mode: 'CASH', payment_stage: 'CHECK_IN' } });

  if (folio.isLoading) return <Spinner />;
  if (folio.isError) return <Err message={apiErrorMessage(folio.error)} />;
  if (!folio.data) return <Empty title="Booking not found" hint="Booking may have been deleted or you do not have access." />;
  const folioData = folio.data;

  const isOverpayment = folioData.balance_due <= 0;

  const paymentError = createPayment.isError
    ? (createPayment.error as { code?: string })?.code === 'ECONNABORTED'
      ? 'Payment timeout — outcome may be unknown. Verify payment history before retrying.'
      : mutationErrorMessage(createPayment.error)
    : null;

  async function downloadReceipt() {
    try {
      const blob = await (await import('@/services/tourism')).downloadStaffReceipt(booking_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${folioData.booking_ref}-receipt.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setReceiptDownloadErr(mutationErrorMessage(e));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Folio — {folioData.booking_ref}</h1>
        <Button type="button" onClick={() => setShowChargeForm((s) => !s)}>{showChargeForm ? 'Close' : 'Add Charge'}</Button>
      </div>
      <p className="text-sm text-stone-500">
        {folioData.booking_status === 'CANCELLED' ? <span className="text-red-600">Cancelled booking</span> : folioData.booking_status}
      </p>
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <p className="text-sm font-medium text-stone-500">Total Charges</p>
          <p className="text-xl font-medium">{folioData.total_charges.toFixed(2)}</p>
        </Card>
        <Card>
          <p className="text-sm font-medium text-stone-500">Total Paid</p>
          <p className="text-xl font-medium">{folioData.total_paid.toFixed(2)}</p>
        </Card>
        <Card>
          <p className="text-sm font-medium text-stone-500">Balance Due</p>
          <p className={`text-xl font-medium ${folioData.balance_due > 0 ? 'text-red-600' : 'text-green-600'}`}>{folioData.balance_due.toFixed(2)}</p>
        </Card>
      </div>

      <div className="mt-4">
        <h2 className="font-medium text-sm">Entries</h2>
        {folioData.entries.length === 0 ? (
          <Empty title="No folio entries yet" />
        ) : (
          <div className="space-y-1">
            {folioData.entries.map((e) => {
              const isReversal = e.entry_type === 'REVERSAL';
              const isDiscount = e.entry_type === 'DISCOUNT';
              return (
                <div key={e.id} className="flex items-center justify-between p-2 rounded-md border border-stone-200 bg-white text-sm">
                  <div className="flex items-center gap-3">
                    <span className="font-medium text-stone-700">{e.entry_type}</span>
                    <span className="text-sm text-stone-600">{e.description}</span>
                    {isReversal && <span className="text-xs text-stone-400">reverses #{e.reverses_entry_id?.slice(0, 8)}</span>}
                  </div>
                  <div className="text-right text-sm">
                    <p className={`font-medium ${isReversal || isDiscount ? 'text-red-600' : 'text-stone-600'}`}>{e.amount.toFixed(2)}</p>
                    <p className="text-xs text-stone-400">{e.created_at}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="mt-4">
        <h2 className="font-medium text-sm">Payments</h2>
        {payments.isLoading ? <Spinner /> : null}
        {payments.isError ? <Err message={apiErrorMessage(payments.error)} /> : null}
        {!payments.isLoading && !payments.isError && (payments.data?.items ?? []).length === 0 ? (
          <Empty title="No payments yet" />
        ) : (
          <div className="space-y-1">
            {payments.data?.items.map((p) => (
              <div key={p.id} className="flex items-center justify-between p-2 rounded-md border border-stone-200 bg-white text-sm">
                <div className="flex items-center gap-3">
                  <span className="font-medium text-stone-700">{p.payment_stage}</span>
                  <span className="text-xs text-stone-400 uppercase">{p.mode}</span>
                  <p className="text-sm text-stone-600">{p.received_at}</p>
                </div>
                <div className="text-right text-sm">
                  <p className={`font-medium ${p.is_reversal ? 'text-red-600' : 'text-stone-600'}`}>{p.amount.toFixed(2)}</p>
                  {p.reference_note && <p className="text-xs text-stone-400">{p.reference_note}</p>}
                </div>
              </div>
            ))}
          </div>
        )}
        {canReadReceipts && receipt.data && (
          <div className="mt-3 flex items-center gap-2">
            <p className="text-xs text-stone-500">Final receipt: {receipt.data.receipt_ref} ({receipt.data.kind})</p>
            <Button type="button" onClick={downloadReceipt}>Download PDF</Button>
            {receiptDownloadErr ? <Err message={receiptDownloadErr} /> : null}
          </div>
        )}
      </div>

      {showChargeForm && canWriteCharges && (
        <div className="mt-4">
          <h2 className="font-medium">Add Additional Charge</h2>
          <form onSubmit={cHandleSubmit((v) => createCharge.mutate({ description: v.description, quantity: v.quantity, unit_amount: v.unit_amount }))} className="mt-3 space-y-3">
            <Field label="Description" error={cErrors.description?.message}><Input {...cRegister('description')} /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Quantity" error={cErrors.quantity?.message}><Input type="number" step="0.01" {...cRegister('quantity')} /></Field>
              <Field label="Unit Amount" error={cErrors.unit_amount?.message}><Input type="number" step="0.01" {...cRegister('unit_amount')} /></Field>
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={createCharge.isPending}>Add Charge</Button>
              <Button type="button" onClick={() => setShowChargeForm(false)}>Cancel</Button>
            </div>
            {cErrors.description ? <Err message={cErrors.description.message ?? ''} /> : null}
            {cErrors.quantity ? <Err message={cErrors.quantity.message ?? ''} /> : null}
            {cErrors.unit_amount ? <Err message={cErrors.unit_amount.message ?? ''} /> : null}
          </form>
        </div>
      )}

      {canWriteDiscounts && (
        <div className="mt-4">
          <Button type="button" onClick={() => setShowDiscountForm((s) => !s)}>{showDiscountForm ? 'Hide' : 'Add Discount'}</Button>
          {showDiscountForm && (
            <div className="mt-3">
              <h2 className="font-medium">Add Discount (ADMIN)</h2>
              <p className="text-xs text-stone-500">ADMIN-only. Reason is mandatory.</p>
              <form onSubmit={dHandleSubmit((v) => createDiscount.mutate({ amount: v.amount, reason: v.reason }))} className="mt-2 space-y-3">
                <Field label="Amount" error={dErrors.amount?.message}><Input type="number" step="0.01" {...dRegister('amount')} /></Field>
                <Field label="Reason" error={dErrors.reason?.message}><Input {...dRegister('reason')} /></Field>
                <div className="flex gap-2">
                  <Button type="submit" disabled={createDiscount.isPending}>Add Discount</Button>
                  <Button type="button" onClick={() => setShowDiscountForm(false)}>Cancel</Button>
                </div>
                {dErrors.amount ? <Err message={dErrors.amount.message ?? ''} /> : null}
                {dErrors.reason ? <Err message={dErrors.reason.message ?? ''} /> : null}
              </form>
            </div>
          )}
        </div>
      )}

      {!canWriteDiscounts && (
        <div className="mt-4 p-3 rounded-md border border-stone-200 bg-stone-50 text-sm text-stone-600">
          Discounts are ADMIN-only. Please ask an administrator to apply a discount.
        </div>
      )}

      <div className="mt-4">
        <h2 className="font-medium">Reverse Entry</h2>
        <p className="text-xs text-stone-500">Reversals append an offsetting entry — the original is never deleted.</p>
        {confirmReversal ? (
          <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-3">
            <p className="text-sm text-red-800 font-medium">Confirm reversal of entry <span className="font-mono">{confirmReversal.slice(0, 8)}…</span>?</p>
            <p className="text-xs text-red-600 mt-1">This cannot be undone. A reversal entry will be appended to the folio.</p>
            <div className="mt-3 flex gap-2">
              <form onSubmit={rcHandleSubmit((v) => { createReversal.mutate({ entry_id: confirmReversal!, reason: v.reason }); setConfirmReversal(null); })} className="space-y-2">
                <Field label="Reason" error={rcErrors.reason?.message}><Input {...rcRegister('reason')} /></Field>
                <div className="flex gap-2">
                  <Button type="submit" disabled={createReversal.isPending} className="bg-red-600 hover:bg-red-700">Confirm Reversal</Button>
                  <Button type="button" onClick={() => setConfirmReversal(null)}>Cancel</Button>
                </div>
                {rcErrors.reason ? <Err message={rcErrors.reason.message ?? ''} /> : null}
              </form>
            </div>
          </div>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); if (reversalEntryIdRef.current?.value) setConfirmReversal(reversalEntryIdRef.current.value); }} className="mt-3 space-y-3">
            <Field label="Entry ID to reverse"><input ref={reversalEntryIdRef} className="w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm" placeholder="e.g. e1" /></Field>
            <div className="flex gap-2">
              <Button type="submit" disabled={createReversal.isPending}>Reverse Entry</Button>
              <Button type="button" onClick={() => reversalEntryIdRef.current = null}>Cancel</Button>
            </div>
          </form>
        )}
      </div>

      <div className="mt-4">
        <h2 className="font-medium">Record Payment</h2>
        {isOverpayment && (
          <p className="text-xs text-stone-500 mb-2">Balance is already zero or negative. Overpayment requires ADMIN authorization with a reason.</p>
        )}
        <form onSubmit={pHandleSubmit((v) => createPayment.mutate({ amount: v.amount, mode: v.mode, payment_stage: v.payment_stage, reference_note: v.reference_note ?? null, overpayment_reason: isOverpayment ? v.overpayment_reason ?? null : null }))} className="mt-3 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Amount" error={pErrors.amount?.message}><Input type="number" step="0.01" {...pRegister('amount')} /></Field>
            <Field label="Mode" error={pErrors.mode?.message}><select {...pRegister('mode')} className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm"><option value="CASH">CASH</option><option value="UPI">UPI</option><option value="CARD_POS">CARD_POS</option></select></Field>
            <Field label="Stage" error={pErrors.payment_stage?.message}><select {...pRegister('payment_stage')} className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm"><option value="ADVANCE">Advance</option><option value="CHECK_IN">Check-In</option><option value="CHECKOUT">Checkout</option><option value="OTHER">Other</option></select></Field>
            <Field label="Reference Note" error={pErrors.reference_note?.message}><Input {...pRegister('reference_note')} /></Field>
            {isOverpayment && (
              <Field label="Overpayment Reason (ADMIN)" error={pErrors.overpayment_reason?.message}><Input {...pRegister('overpayment_reason')} /></Field>
            )}
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={createPayment.isPending}>{createPayment.isPending ? 'Recording…' : 'Record Payment'}</Button>
            <Button type="button">Cancel</Button>
          </div>
          {pErrors.amount ? <Err message={pErrors.amount.message ?? ''} /> : null}
          {pErrors.mode ? <Err message={pErrors.mode.message ?? ''} /> : null}
          {pErrors.payment_stage ? <Err message={pErrors.payment_stage.message ?? ''} /> : null}
          {pErrors.reference_note ? <Err message={pErrors.reference_note.message ?? ''} /> : null}
          {pErrors.overpayment_reason ? <Err message={pErrors.overpayment_reason.message ?? ''} /> : null}
        </form>
        {paymentError && <Err message={paymentError} />}
      </div>

      {err ? <Err message={err} /> : null}
    </div>
  );
}
