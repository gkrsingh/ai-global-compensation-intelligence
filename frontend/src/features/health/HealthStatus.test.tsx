import { render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { HealthStatus } from './HealthStatus';

describe('HealthStatus', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders ok status when the backend and database are healthy', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        json: () => Promise.resolve({ status: 'ok', checks: { api: 'ok', database: 'ok' } }),
      }),
    );

    const { container } = render(<HealthStatus />);

    await waitFor(() => {
      expect(container.textContent).toContain('Overall status: ok');
    });
    expect(container.textContent).toContain('database: ok');
  });

  it('renders degraded status when the database is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        json: () =>
          Promise.resolve({ status: 'degraded', checks: { api: 'ok', database: 'error' } }),
      }),
    );

    const { container } = render(<HealthStatus />);

    await waitFor(() => {
      expect(container.textContent).toContain('Overall status: degraded');
    });
    expect(container.textContent).toContain('database: error');
  });
});
