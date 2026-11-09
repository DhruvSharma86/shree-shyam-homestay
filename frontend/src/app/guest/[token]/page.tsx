// Guest pages are bearer-token gated and must never be statically cached.
// Server wrapper awaits `params` (Next 16 async params) and hands the
// token to the client tree.
export const instant = false;

import { GuestPortalView } from './view';

export default async function GuestPortalPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <GuestPortalView token={token} />;
}
