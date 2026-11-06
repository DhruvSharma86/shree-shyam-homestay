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
