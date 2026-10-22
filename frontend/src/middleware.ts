import { NextResponse, type NextRequest } from "next/server";

/** Coarse gate: no session cookie at all -> sign-in page. Real authorization
 *  happens in the API on every request. */
export function middleware(req: NextRequest) {
  const hasSession = req.cookies.has("strata_at") || req.cookies.has("strata_session");
  const { pathname } = req.nextUrl;
  if (!hasSession && pathname !== "/login") {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api/|_next/|brand/|icon.svg|favicon.ico|robots.txt).*)"],
};
