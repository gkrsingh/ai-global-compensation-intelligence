import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

import {
  login as apiLogin,
  logoutRequest as apiLogout,
  refreshAccessToken as apiRefresh,
  register as apiRegister,
} from '../../api/client';
import {
  clearPersistedSession,
  getStoredEmail,
  getStoredRefreshToken,
  persistSession,
  setAccessToken,
} from '../../api/tokenStore';

interface AuthState {
  status: 'loading' | 'authenticated' | 'anonymous';
  email: string | null;
}

export interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  // Called when the calculate endpoint reports a rejected token (see
  // CreateCalculationResult.authWarning), so the UI reflects "you got
  // logged out" immediately rather than staying stuck showing a stale
  // "logged in" state until the next action that happens to fail.
  handleAuthWarning: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading', email: null });

  useEffect(() => {
    const refreshToken = getStoredRefreshToken();
    if (!refreshToken) {
      setState({ status: 'anonymous', email: null });
      return;
    }
    apiRefresh(refreshToken)
      .then(({ access_token }) => {
        setAccessToken(access_token);
        setState({ status: 'authenticated', email: getStoredEmail() });
      })
      .catch(() => {
        // The stored refresh token is dead (expired/revoked) - fall back
        // to anonymous rather than leaving the app stuck on "loading".
        clearPersistedSession();
        setAccessToken(null);
        setState({ status: 'anonymous', email: null });
      });
  }, []);

  async function login(email: string, password: string) {
    const tokens = await apiLogin(email, password);
    setAccessToken(tokens.access_token);
    persistSession(tokens.refresh_token, email);
    setState({ status: 'authenticated', email });
  }

  async function register(email: string, password: string) {
    await apiRegister(email, password);
    // The backend deliberately keeps register and login separate (one
    // job per endpoint - register creates the account, login is the only
    // place tokens get issued). Auto-logging-in here is a frontend-only
    // UX choice on top of that, not a change to the backend's contract -
    // nobody wants to type the same password twice in a row.
    await login(email, password);
  }

  async function logout() {
    const refreshToken = getStoredRefreshToken();
    if (refreshToken) {
      // Best-effort: if the revoke call fails (e.g. already expired),
      // still clear local state - the user's intent to log out locally
      // shouldn't depend on the backend call succeeding.
      await apiLogout(refreshToken).catch(() => undefined);
    }
    setAccessToken(null);
    clearPersistedSession();
    setState({ status: 'anonymous', email: null });
  }

  function handleAuthWarning() {
    setAccessToken(null);
    clearPersistedSession();
    setState({ status: 'anonymous', email: null });
  }

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, handleAuthWarning }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
