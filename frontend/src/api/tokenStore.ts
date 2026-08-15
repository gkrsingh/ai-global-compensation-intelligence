/**
 * Token storage tradeoff (stated explicitly, not a style choice):
 *
 * The access token (15 min) lives ONLY in memory - a plain module
 * variable, never written to any Web Storage API. Lost on page reload,
 * but that costs nothing in practice: the app re-fetches it via the
 * refresh token on load.
 *
 * The refresh token (30 days) lives in localStorage. That's the real
 * tradeoff: localStorage is fully readable by any JS on the page,
 * including via XSS, so a compromised dependency or a future XSS bug
 * could exfiltrate it and impersonate the user for up to 30 days. The
 * safer alternative - an httpOnly cookie the frontend can never read at
 * all - would require reworking the already-shipped backend token
 * contract (Set-Cookie instead of a JSON field, CSRF mitigation since
 * cookies auto-attach cross-site), which is a backend decision, not a
 * frontend storage one. Accepted here because this is a personal-use
 * tool (not a multi-tenant product with adversarial users), the backend
 * already supports revocation, and the "stay logged in across reloads"
 * UX is worth it. httpOnly cookies remain the correct hardening path if
 * this project's risk profile ever changes.
 */

let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

const REFRESH_TOKEN_KEY = 'compintel.refreshToken';
// Not sensitive on its own (just an email string, no credential) - kept
// alongside the refresh token purely so the UI can show "logged in as
// ..." after a reload without an extra round trip to ask the backend who
// the token belongs to.
const EMAIL_KEY = 'compintel.email';

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function getStoredEmail(): string | null {
  return localStorage.getItem(EMAIL_KEY);
}

export function persistSession(refreshToken: string, email: string): void {
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  localStorage.setItem(EMAIL_KEY, email);
}

export function clearPersistedSession(): void {
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
}
