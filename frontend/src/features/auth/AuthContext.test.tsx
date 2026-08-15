import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getAccessToken, persistSession } from '../../api/tokenStore';
import { stubFetch } from '../../test/apiMocks';
import { AuthProvider, useAuth } from './AuthContext';

function Probe() {
  const { status, email, login, register, logout, handleAuthWarning } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="email">{email ?? ''}</span>
      <button onClick={() => void login('probe@example.com', 'correct horse battery staple')}>
        login
      </button>
      <button onClick={() => void register('probe@example.com', 'correct horse battery staple')}>
        register
      </button>
      <button onClick={() => void logout()}>logout</button>
      <button onClick={handleAuthWarning}>auth-warning</button>
    </div>
  );
}

function renderProbe() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

describe('AuthProvider', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('resolves to anonymous immediately when no session is stored', async () => {
    stubFetch({});

    renderProbe();

    expect(await screen.findByTestId('status')).toHaveTextContent('anonymous');
  });

  it('silently restores an authenticated session from a valid stored refresh token', async () => {
    persistSession('stored-refresh-token', 'restored@example.com');
    stubFetch({ refresh: { access_token: 'new-access-token', token_type: 'bearer' } });

    renderProbe();

    expect(await screen.findByTestId('status')).toHaveTextContent('authenticated');
    expect(screen.getByTestId('email')).toHaveTextContent('restored@example.com');
    expect(getAccessToken()).toBe('new-access-token');
  });

  it('falls back to anonymous and clears storage when the stored refresh token is dead', async () => {
    persistSession('a-dead-refresh-token', 'stale@example.com');
    stubFetch({
      refresh: {
        status: 401,
        body: { error: { code: 'invalid_refresh_token', message: 'bad', details: null } },
      },
    });

    renderProbe();

    expect(await screen.findByTestId('status')).toHaveTextContent('anonymous');
    expect(getAccessToken()).toBeNull();
  });

  it('login sets authenticated status and stores the token pair', async () => {
    stubFetch({
      login: {
        access_token: 'login-access-token',
        refresh_token: 'login-refresh-token',
        token_type: 'bearer',
      },
    });

    renderProbe();
    await screen.findByTestId('status');

    fireEvent.click(screen.getByText('login'));

    expect(await screen.findByTestId('status')).toHaveTextContent('authenticated');
    expect(screen.getByTestId('email')).toHaveTextContent('probe@example.com');
    expect(getAccessToken()).toBe('login-access-token');
  });

  it('register creates the account then logs in (two calls, one resulting session)', async () => {
    stubFetch({
      register: { id: 1, email: 'probe@example.com', created_at: '2026-08-16T00:00:00Z' },
      login: {
        access_token: 'register-access-token',
        refresh_token: 'register-refresh-token',
        token_type: 'bearer',
      },
    });

    renderProbe();
    await screen.findByTestId('status');

    fireEvent.click(screen.getByText('register'));

    expect(await screen.findByTestId('status')).toHaveTextContent('authenticated');
    expect(getAccessToken()).toBe('register-access-token');
  });

  it('logout clears the session back to anonymous', async () => {
    stubFetch({
      login: {
        access_token: 'login-access-token',
        refresh_token: 'login-refresh-token',
        token_type: 'bearer',
      },
    });

    renderProbe();
    await screen.findByTestId('status');
    fireEvent.click(screen.getByText('login'));
    await screen.findByText('authenticated');

    fireEvent.click(screen.getByText('logout'));

    expect(await screen.findByTestId('status')).toHaveTextContent('anonymous');
    expect(getAccessToken()).toBeNull();
  });

  it('handleAuthWarning clears the session without calling the backend', async () => {
    stubFetch({
      login: {
        access_token: 'login-access-token',
        refresh_token: 'login-refresh-token',
        token_type: 'bearer',
      },
    });

    renderProbe();
    await screen.findByTestId('status');
    fireEvent.click(screen.getByText('login'));
    await screen.findByText('authenticated');

    fireEvent.click(screen.getByText('auth-warning'));

    expect(await screen.findByTestId('status')).toHaveTextContent('anonymous');
    expect(getAccessToken()).toBeNull();
  });
});
