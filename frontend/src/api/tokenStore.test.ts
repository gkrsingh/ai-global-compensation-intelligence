import { afterEach, describe, expect, it } from 'vitest';

import {
  clearPersistedSession,
  getAccessToken,
  getStoredEmail,
  getStoredRefreshToken,
  persistSession,
  setAccessToken,
} from './tokenStore';

describe('tokenStore', () => {
  afterEach(() => {
    setAccessToken(null);
    localStorage.clear();
  });

  it('holds the access token in memory only, not in any Web Storage API', () => {
    expect(getAccessToken()).toBeNull();

    setAccessToken('a-real-looking-access-token');

    expect(getAccessToken()).toBe('a-real-looking-access-token');
    expect(localStorage.getItem('compintel.accessToken')).toBeNull();
    expect(sessionStorage.getItem('compintel.accessToken')).toBeNull();
  });

  it('persists the refresh token and email to localStorage', () => {
    persistSession('a-refresh-token', 'user@example.com');

    expect(getStoredRefreshToken()).toBe('a-refresh-token');
    expect(getStoredEmail()).toBe('user@example.com');
  });

  it('clears both the refresh token and email together', () => {
    persistSession('a-refresh-token', 'user@example.com');

    clearPersistedSession();

    expect(getStoredRefreshToken()).toBeNull();
    expect(getStoredEmail()).toBeNull();
  });
});
