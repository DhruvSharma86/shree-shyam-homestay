import { z } from 'zod';
export const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
});
export const hotelSchema = z.object({
  hotel_name: z.string().min(1, 'Hotel name is required'),
  description: z.string().optional(),
  address: z.string().optional(),
  city: z.string().max(120).optional(),
  state: z.string().max(120).optional(),
  pincode: z.string().max(16).optional(),
  contact_number: z.string().max(24).optional(),
  alternate_contact_number: z.string().max(24).optional(),
  email: z.union([z.string().email('Invalid email'), z.literal('')]).optional(),
  google_maps_url: z.string().url('Must be a URL').optional().or(z.literal('')),
  website_url: z.string().url('Must be a URL').optional().or(z.literal('')),
  logo_url: z.string().url('Must be a URL').optional().or(z.literal('')),
  check_in_time: z.string().max(8).optional(),
  check_out_time: z.string().max(8).optional(),
  wifi_ssid: z.string().max(64).optional(),
  wifi_password: z.string().max(128).optional(),
});
export const roomTypeSchema = z.object({
  name: z.string().min(1, 'Name is required').max(64),
  description: z.string().optional(),
  maximum_occupancy: z.coerce.number().int().min(1).max(20),
  amenities: z.string().optional(),
  display_order: z.coerce.number().int(),
});
export const roomSchema = z.object({
  room_number: z.string().min(1, 'Room number is required').max(16),
  room_type_id: z.string().min(1, 'Room type is required'),
  floor: z.coerce.number().int().optional(),
  description: z.string().optional(),
  maximum_occupancy: z.coerce.number().int().min(1).max(20),
});
export const roomPatchSchema = z.object({
  room_type_id: z.string().min(1).optional(),
  floor: z.coerce.number().int().optional(),
  description: z.string().optional(),
  maximum_occupancy: z.coerce.number().int().min(1).max(20).optional(),
  operational_status: z.enum(['AVAILABLE', 'MAINTENANCE', 'INACTIVE']).optional(),
  is_active: z.boolean().optional(),
});
export const rateSchema = z.object({
  room_type_id: z.string().min(1, 'Room type is required'),
  nightly_rate: z.string().regex(/^\d+(\.\d{1,2})?$/, 'Enter a non-negative amount'),
  valid_from: z.string().min(1, 'Start date is required'),
  valid_until: z.string().optional(),
});
export const taxSchema = z.object({
  registration_status: z.string(),
  tax_type: z.string(),
  tax_rate: z.string().regex(/^\d+(\.\d{1,2})?$/, 'Enter a non-negative rate').optional().or(z.literal('')),
  pricing_mode: z.enum(['INCLUSIVE', 'EXCLUSIVE']),
  valid_from: z.string().min(1, 'Start date is required'),
  valid_until: z.string().optional(),
  notes: z.string().optional(),
});
export const restaurantSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  contact_number: z.string().max(24).optional(),
  opening_hours: z.string().optional(),
  is_active: z.boolean(),
});
export const menuCategorySchema = z.object({
  name: z.string().min(1, 'Name is required').max(120),
  description: z.string().optional(),
  display_order: z.coerce.number().int(),
});
export const menuItemSchema = z.object({
  name: z.string().min(1, 'Name is required').max(160),
  description: z.string().optional(),
  price: z.string().regex(/^\d+(\.\d{1,2})?$/, 'Enter a non-negative price'),
  image_url: z.string().url('Must be a URL').optional().or(z.literal('')),
  category_id: z.string().min(1, 'Category is required'),
  is_vegetarian: z.boolean(),
  display_order: z.coerce.number().int(),
});
export const cabSchema = z.object({
  company_name: z.string().min(1, 'Company name is required'),
  description: z.string().optional(),
  contact_number: z.string().min(7, 'Phone too short').max(24),
  website_url: z.string().url('Must be a URL').optional().or(z.literal('')),
  service_description: z.string().optional(),
  display_order: z.coerce.number().int(),
});
export const userCreateSchema = z.object({
  username: z.string().min(1).max(64),
  password: z.string().min(10, 'Password must be at least 10 characters'),
  full_name: z.string().min(1).max(120),
  role: z.enum(['ADMIN', 'RECEPTIONIST']),
  email: z.string().email().optional().or(z.literal('')),
});
export const tourPackageSchema = z.object({
  name: z.string().min(1, 'Name is required').max(160),
  description: z.string().optional(),
  duration: z.string().max(64).optional(),
  price: z.string().regex(/^\d+(\.\d{1,2})?$/, 'Enter a non-negative price').optional().or(z.literal('')),
  image_url: z.string().url('Must be a URL').optional().or(z.literal('')),
  contact_number: z.union([z.string().min(7, 'Phone too short').max(24), z.literal('')]).optional(),
  display_order: z.coerce.number().int(),
});
export const localInfoSchema = z.object({
  title: z.string().min(1, 'Title is required').max(160),
  description: z.string().optional(),
  location: z.string().max(255).optional(),
  contact_number: z.union([z.string().min(7, 'Phone too short').max(24), z.literal('')]).optional(),
  image_url: z.string().url('Must be a URL').optional().or(z.literal('')),
  display_order: z.coerce.number().int(),
});
export type LoginForm = z.infer<typeof loginSchema>;
export type HotelForm = z.infer<typeof hotelSchema>;
