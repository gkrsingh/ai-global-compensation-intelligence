import { useState, type FormEvent } from 'react';

import { ApiError } from '../../api/client';
import { friendlyErrorLines } from '../../api/errors';
import { useAuth } from './AuthContext';

export interface AuthFormsProps {
  onSuccess: () => void;
}

export function AuthForms({ onSuccess }: AuthFormsProps) {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const action = mode === 'login' ? login(email, password) : register(email, password);
    action
      .then(() => {
        onSuccess();
      })
      .catch((err: unknown) => {
        setSubmitting(false);
        setError(
          err instanceof ApiError
            ? err
            : new ApiError('unknown_error', 'Something went wrong', null),
        );
      });
  }

  function switchMode() {
    setMode((current) => (current === 'login' ? 'register' : 'login'));
    setError(null);
  }

  return (
    <section>
      <h2>{mode === 'login' ? 'Log in' : 'Register'}</h2>

      {error && (
        <div role="alert" className="error-banner">
          <ul>
            {friendlyErrorLines(error).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="field">
          <label htmlFor="auth-email">Email</label>
          <input
            id="auth-email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="auth-password">Password</label>
          <input
            id="auth-password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        <button type="submit" disabled={submitting}>
          {submitting ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Register'}
        </button>
      </form>

      <p>
        {mode === 'login' ? (
          <>
            Don&apos;t have an account?{' '}
            <button type="button" className="link-button" onClick={switchMode}>
              Register
            </button>
          </>
        ) : (
          <>
            Already have an account?{' '}
            <button type="button" className="link-button" onClick={switchMode}>
              Log in
            </button>
          </>
        )}
      </p>
    </section>
  );
}
