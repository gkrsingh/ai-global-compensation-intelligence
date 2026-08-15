import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CalculationOut } from '../../api/client';
import { stubFetch } from '../../test/apiMocks';
import { HistoryView } from './HistoryView';

function calculation(id: number, grossAmount: string): CalculationOut {
  return {
    id,
    compensation_input_id: id,
    user_id: 1,
    engine_version: '1.0.0',
    gross_amount: grossAmount,
    total_compensation_amount: grossAmount,
    tax_rule_set_id: null,
    total_tax_amount: null,
    net_amount: null,
    breakdown: {
      target_currency: 'USD',
      as_of_date: '2026-08-16',
      rates_used: {},
      components: [],
      tax: null,
    },
    created_at: '2026-08-16T00:00:00Z',
  };
}

describe('HistoryView', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows an empty-state message when the user has no saved calculations', async () => {
    stubFetch({ myCalculations: { items: [], total: 0, limit: 10, offset: 0 } });

    render(<HistoryView />);

    expect(await screen.findByText("You haven't saved any calculations yet.")).toBeInTheDocument();
  });

  it('lists calculations and shows the full breakdown when one is selected', async () => {
    stubFetch({
      myCalculations: {
        items: [calculation(1, '50000.00')],
        total: 1,
        limit: 10,
        offset: 0,
      },
    });

    render(<HistoryView />);
    const row = await screen.findByRole('button', { name: /Gross: \$50,000\.00/ });

    fireEvent.click(row);

    expect(await screen.findByText('Result')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'New calculation' }));

    expect(await screen.findByRole('button', { name: /Gross: \$50,000\.00/ })).toBeInTheDocument();
  });

  it('disables Previous on the first page and requests the next offset when Next is clicked', async () => {
    const fetchSpy = stubFetch({
      myCalculations: {
        items: [calculation(1, '1000.00'), calculation(2, '2000.00')],
        total: 5,
        limit: 10,
        offset: 0,
      },
    });

    render(<HistoryView />);
    await screen.findByRole('button', { name: /Gross: \$1,000\.00/ });

    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => {
      // HistoryView always requests with its own fixed PAGE_SIZE (10),
      // independent of whatever `limit` a mocked response happens to
      // echo back.
      const lastCall = fetchSpy.mock.calls.at(-1);
      expect(String(lastCall?.[0])).toContain('offset=10');
    });
  });
});
