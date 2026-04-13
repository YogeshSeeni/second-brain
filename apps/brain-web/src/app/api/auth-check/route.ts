import { NextResponse } from "next/server";
import { auth } from "@/auth";

// Called by Caddy's forward_auth before it proxies /api/* to brain-core.
// Returns 200 if the request carries a valid NextAuth session, 401 otherwise.
export async function GET() {
  const session = await auth();
  if (!session?.user?.email) {
    return new NextResponse(null, { status: 401 });
  }
  return new NextResponse(null, { status: 200 });
}
