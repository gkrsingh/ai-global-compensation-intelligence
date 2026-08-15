import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

import { setAccessToken } from '../api/tokenStore';

// @testing-library/react's auto-cleanup only registers itself when it
// detects a *global* afterEach (typeof afterEach === 'function' at import
// time). This project doesn't set `globals: true` in vite.config.ts, so
// that check silently no-ops - every render() across every test in a file
// stayed mounted, and any test using `screen` (rather than the scoped
// `container` HealthStatus.test.tsx happened to use) would find multiple
// matching elements from earlier tests. Registering cleanup explicitly
// here fixes it for every test file, not just the one that surfaced it.
afterEach(() => {
  cleanup();
  // AuthProvider persists the refresh token/email to localStorage, which
  // JSDOM keeps alive across tests in the same file otherwise - without
  // this, a session written by one test would silently leak into the
  // next test's AuthProvider mount.
  localStorage.clear();
  // The in-memory access token (tokenStore.ts) is plain module state,
  // which Vitest does NOT reset between tests in the same file by
  // default - same leak risk as localStorage above, just in memory
  // instead of storage.
  setAccessToken(null);
});
