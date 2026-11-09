// Guest-portal types (bearer-token views — no internal ids, no money, no PII).
export interface GuestOverview {
  hotel_name: string;
  booking_ref: string;
  room_number: string;
  room_type: string;
  check_in_date: string;
  check_out_date: string;
  nights: number;
  status: string;
  checked_out_at: string | null;
  expires_at: string | null;
  contact: { contact_number: string | null; email: string | null; address: string | null };
}
export interface GuestMenuItem {
  name: string;
  description: string | null;
  price: string;
  image_url: string | null;
  is_vegetarian: boolean;
}
export interface GuestMenuCategory { category: string; items: GuestMenuItem[]; }
export interface GuestMenu { categories: GuestMenuCategory[]; }
export interface GuestCabProvider {
  company_name: string;
  description: string | null;
  contact_number: string;
  service_description: string | null;
}
export interface GuestCab { providers: GuestCabProvider[]; }
export interface GuestWifi { ssid: string | null; password: string | null; }
export interface GuestReceiptInfo {
  receipt_ref: string;
  kind: string;
  content_hash: string;
}
export interface GuestTourPackage {
  name: string;
  description: string | null;
  duration: string | null;
  price: string | null;
  image_url: string | null;
  contact_number: string | null;
}
export interface GuestLocalInfo {
  title: string;
  description: string | null;
  location: string | null;
  contact_number: string | null;
  image_url: string | null;
}
export interface GuestTourism {
  packages: GuestTourPackage[];
  local_info: GuestLocalInfo[];
}

// Staff booking check-in delivery (check-in response carries the raw token once).
export interface CheckInResult {
  booking_id: string;
  booking_ref: string;
  status: string;
  checked_in_at: string | null;
  portal_access_token: string;
}
export interface BookingSummary {
  id: string;
  booking_ref: string;
  status: string;
  check_in_date: string;
  check_out_date: string;
  nights: number;
}
export interface BookingList {
  items: BookingSummary[];
  total: number;
  page: number;
  page_size: number;
}
export interface BookingDetail extends BookingSummary {
  guest_id: string;
  room_id: string;
  room_type_id: string;
  source: string;
  number_of_guests: number;
  notes: string | null;
  night_rate_snapshot: string;
  rate_id: string | null;
  room_subtotal: string;
  tax_type_snapshot: string;
  tax_rate_snapshot: string | null;
  tax_pricing_mode_snapshot: string;
  total_amount: string;
  cancelled_at: string | null;
  cancellation_reason: string | null;
}
export interface TourismPackageAdmin {
  id: string;
  name: string;
  description: string | null;
  duration: string | null;
  price: string | null;
  image_url: string | null;
  contact_number: string | null;
  is_active: boolean;
  display_order: number;
}
export interface LocalInfoAdmin {
  id: string;
  title: string;
  description: string | null;
  location: string | null;
  contact_number: string | null;
  image_url: string | null;
  is_active: boolean;
  display_order: number;
}
