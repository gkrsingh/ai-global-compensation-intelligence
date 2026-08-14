import { useEffect, useState } from 'react';

import { fetchHealth, type HealthCheckResponse } from '../../api/client';

type LoadState =
  | { kind: 'loading' }
  | { kind: 'loaded'; data: HealthCheckResponse }
  | { kind: 'error'; message: string };

export function HealthStatus() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' });

  useEffect(() => {
    let cancelled = false;

    fetchHealth()
      .then((data) => {
        if (!cancelled) setState({ kind: 'loaded', data });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : 'Unknown error';
          setState({ kind: 'error', message });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (state.kind === 'loading') {
    return <p>Checking backend status…</p>;
  }

  if (state.kind === 'error') {
    return <p role="alert">Backend unreachable: {state.message}</p>;
  }

  const { status, checks } = state.data;

  return (
    <div>
      <p>
        Overall status: <strong>{status}</strong>
      </p>
      <ul>
        {Object.entries(checks).map(([name, value]) => (
          <li key={name}>
            {name}: {value}
          </li>
        ))}
      </ul>
    </div>
  );
}
