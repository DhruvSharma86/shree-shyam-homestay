import { describe, it, expect } from 'vitest';
import { loginSchema, rateSchema, taxSchema, cabSchema } from '@/schemas';

describe('schemas', () => {
  it('login requires username and password', () => {
    expect(loginSchema.safeParse({ username: '', password: '' }).success).toBe(false);
    expect(loginSchema.safeParse({ username: 'a', password: 'b' }).success).toBe(true);
  });
  it('rate rejects negative prices', () => {
    expect(rateSchema.safeParse({ room_type_id: 'x', nightly_rate: '-5', valid_from: '2026-11-05' }).success).toBe(false);
    expect(rateSchema.safeParse({ room_type_id: 'x', nightly_rate: '2500.00', valid_from: '2026-11-05' }).success).toBe(true);
  });
  it('cab validates phone and url', () => {
    expect(cabSchema.safeParse({ company_name: 'C', contact_number: '123', display_order: 0 }).success).toBe(false);
    expect(cabSchema.safeParse({ company_name: 'C', contact_number: '1234567890', display_order: 0 }).success).toBe(true);
  });
  it('tax with rate passes', () => {
    expect(taxSchema.safeParse({ registration_status: 'NONE', tax_type: 'NONE', pricing_mode: 'EXCLUSIVE', valid_from: '2026-11-05' }).success).toBe(true);
  });
});
