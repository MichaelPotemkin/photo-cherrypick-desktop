// Clean-URL routing helpers (History API). Pure functions so they're unit-testable without a DOM.

// "/session/<uuid>" -> the session id; anything else -> null.
export function parseSessionId(pathname: string): string | null {
  const m = pathname.match(/^\/session\/([0-9a-fA-F-]+)/);
  return m ? m[1] : null;
}
