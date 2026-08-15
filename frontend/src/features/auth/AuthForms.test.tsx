import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { stubFetch } from '../../test/apiMocks';
import { AuthForms } from './AuthForms';
import { AuthProvider } from './AuthContext';

function renderAuthForms(onSuccess = vi.fn()) {
  render(
    <AuthProvider>
      <AuthForms onSuccess={onSuccess} />
    </AuthProvider>,
  );
  return onSuccess;
}

describe('AuthForms', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('defaults to login mode and can switch to register', () => {
    stubFetch({});
    renderAuthForms();

    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Register' }));

    expect(screen.getByRole('heading', { name: 'Register' })).toBeInTheDocument();
  });

  it('calls onSuccess after a successful login', async () => {
    stubFetch({
      login: {
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        token_type: 'bearer',
      },
    });
    const onSuccess = renderAuthForms();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'correct horse battery staple' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });

  it('shows the friendly error message on wrong credentials, without calling onSuccess', async () => {
    stubFetch({
      login: {
        status: 401,
        body: {
          error: {
            code: 'invalid_credentials',
            message: 'Invalid email or password',
            details: null,
          },
        },
      },
    });
    const onSuccess = renderAuthForms();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }));

    expect(await screen.findByText('Invalid email or password')).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('register mode calls onSuccess after register + auto-login both succeed', async () => {
    stubFetch({
      register: { id: 1, email: 'new-user@example.com', created_at: '2026-08-16T00:00:00Z' },
      login: {
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        token_type: 'bearer',
      },
    });
    const onSuccess = renderAuthForms();

    fireEvent.click(screen.getByRole('button', { name: 'Register' }));
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'new-user@example.com' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'correct horse battery staple' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Register' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });
});
