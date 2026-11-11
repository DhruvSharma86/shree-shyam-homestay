import FolioPage from '@/app/admin/bookings/folio';

export default function FolioRoutePage({ params }: { params: { booking_id: string } }) {
  return <FolioPage booking_id={params.booking_id} />;
}
