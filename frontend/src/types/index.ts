export interface UserResponse {
  id: string;
  username: string;
  email: string | null;
  full_name: string;
  role: 'ADMIN' | 'RECEPTIONIST';
  is_active: boolean;
  last_login_at: string | null;
}
export interface MeResponse { user: UserResponse; permissions: string[]; }
export interface HotelInfo {
  id: string; hotel_name: string; description: string | null; address: string | null;
  city: string | null; state: string | null; pincode: string | null;
  contact_number: string | null; alternate_contact_number: string | null; email: string | null;
  google_maps_url: string | null; website_url: string | null; logo_url: string | null;
  check_in_time: string | null; check_out_time: string | null; wifi_ssid: string | null;
}
export interface RoomType { id: string; name: string; description: string | null; maximum_occupancy: number; amenities: string | null; is_active: boolean; display_order: number; }
export interface Room { id: string; room_number: string; room_type_id: string; floor: number | null; description: string | null; maximum_occupancy: number; operational_status: 'AVAILABLE' | 'MAINTENANCE' | 'INACTIVE'; is_active: boolean; }
export interface RoomRate { id: string; room_type_id: string; nightly_rate: string; valid_from: string; valid_until: string | null; is_active: boolean; }
export interface TaxSettings { id: string; registration_status: string; tax_type: string; tax_rate: string | null; pricing_mode: string; valid_from: string; valid_until: string | null; notes: string | null; }
export interface Restaurant { id: string; name: string; description: string | null; contact_number: string | null; opening_hours: string | null; is_active: boolean; }
export interface MenuCategory { id: string; name: string; description: string | null; display_order: number; is_active: boolean; }
export interface MenuItem { id: string; name: string; description: string | null; price: string; image_url: string | null; category_id: string; is_vegetarian: boolean; is_available: boolean; display_order: number; }
export interface CabProvider { id: string; company_name: string; description: string | null; contact_number: string; website_url: string | null; service_description: string | null; is_active: boolean; display_order: number; }
export interface ApiError { error: { code: string; message: string; details?: unknown } }
export interface Guest { id: string; full_name: string; phone: string; email: string | null; address: string | null; notes: string | null; is_active: boolean; created_at: string; updated_at: string; }
export interface FolioEntryResponse {
  id: string;
  booking_id: string;
  entry_type: string;
  description: string;
  quantity: number;
  unit_amount: number | null;
  amount: number;
  is_initial: boolean;
  reverses_entry_id: string | null;
  created_at: string;
}
export interface FolioResponse {
  booking_id: string;
  booking_ref: string;
  booking_status: string;
  entries: FolioEntryResponse[];
  total_charges: number;
  total_paid: number;
  balance_due: number;
  payment_count: number;
}
export interface ChargeCreate {
  description: string;
  quantity: number;
  unit_amount: number;
}
export interface DiscountCreate {
  amount: number;
  reason: string;
}
export interface ReversalCreate {
  entry_id: string;
  reason: string;
}
export interface PaymentResponse {
  id: string;
  booking_id: string;
  amount: number;
  mode: 'CASH' | 'UPI' | 'CARD_POS';
  payment_stage: 'ADVANCE' | 'CHECK_IN' | 'CHECKOUT' | 'OTHER';
  reference_note: string | null;
  is_reversal: boolean;
  reverses_payment_id: string | null;
  received_at: string;
}
export interface PaymentListResponse {
  items: PaymentResponse[];
  total: number;
  page: number;
  page_size: number;
}
export interface ReceiptResponse {
  receipt_id: string;
  booking_id: string;
  receipt_ref: string;
  kind: string;
  content_hash: string;
}

// Report types (all backend-calculated, never computed in frontend)

export interface FinancialSummaryResponse {
  from_date: string | null;
  to_date: string | null;
  room_charges: number;
  additional_charges: number;
  discounts: number;
  charge_reversals: number;
  gross_charges: number;
  net_payments: number;
  outstanding: number;
}

export interface CollectionRow {
  date: string;
  method: string;
  stage: string;
  transactions: number;
  original_total: number;
  reversal_total: number;
  net_total: number;
}

export interface CollectionReportResponse {
  from_date: string | null;
  to_date: string | null;
  rows: CollectionRow[];
  original_total: number;
  reversal_total: number;
  net_total: number;
}

export interface MethodRow {
  method: string;
  transactions: number;
  original_total: number;
  reversal_total: number;
  net_total: number;
}

export interface MethodReportResponse {
  from_date: string | null;
  to_date: string | null;
  rows: MethodRow[];
  original_total: number;
  reversal_total: number;
  net_total: number;
}

export interface OutstandingRow {
  booking_id: string;
  booking_ref: string;
  room_number: string;
  status: string;
  total_charges: number;
  net_paid: number;
  balance: number;
}

export interface OutstandingReportResponse {
  snapshot: string;
  rows: OutstandingRow[];
  outstanding_total: number;
  credit_total: number;
  total: number;
  page: number;
  page_size: number;
}

export interface ReconciliationResponse {
  from_date: string | null;
  to_date: string | null;
  charge_entries: number;
  original_payments: number;
  reversal_payments: number;
  net_payments: number;
  outstanding_in_period: number;
  credit_in_period: number;
  entry_count: number;
  payment_count: number;
  reversal_count: number;
}

export interface ReversalItem {
  kind: string;
  id: string;
  booking_id: string;
  booking_ref: string;
  amount: number;
  reason: string | null;
  reverses_id: string;
  created_at: string;
}

export interface ReversalsReportResponse {
  from_date: string | null;
  to_date: string | null;
  payment_reversal_total: number;
  charge_reversal_total: number;
  items: ReversalItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface BookingsSummaryResponse {
  from_date: string | null;
  to_date: string | null;
  total: number;
  confirmed: number;
  checked_in: number;
  checked_out: number;
  cancelled: number;
}

export interface OccupancyResponse {
  from_date: string | null;
  to_date: string | null;
  occupied_room_nights: number;
  available_room_nights: number;
  occupancy_rate: number;
}
export * from './guestPortal';
