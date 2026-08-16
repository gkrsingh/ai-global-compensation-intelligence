import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ComparisonDetailOut } from '../../api/client';
import { COUNTRIES, stubFetch } from '../../test/apiMocks';
import { ComparisonsView } from './ComparisonsView';

const DETAIL: ComparisonDetailOut = {
  id: 3,
  name: 'India vs Spain',
  comparison_currency: 'EUR',
  as_of_date: '2026-08-16',
  created_at: '2026-08-16T00:00:00Z',
  entries: [],
  gap_analysis: { gross_amount: null, total_compensation_amount: null, net_amount: null },
  calculations: [],
};

describe('ComparisonsView', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows an empty-state message when the user has no saved comparisons', async () => {
    stubFetch({ myComparisons: { items: [], total: 0, limit: 10, offset: 0 } });

    render(<ComparisonsView />);

    expect(await screen.findByText("You haven't created any comparisons yet.")).toBeInTheDocument();
  });

  it('lists past comparisons and opens one on click', async () => {
    stubFetch({
      myComparisons: {
        items: [
          {
            id: 3,
            name: 'India vs Spain',
            comparison_currency: 'EUR',
            as_of_date: '2026-08-16',
            created_at: '2026-08-16T00:00:00Z',
            calculation_count: 2,
          },
        ],
        total: 1,
        limit: 10,
        offset: 0,
      },
      getComparison: { '3': DETAIL },
    });

    render(<ComparisonsView />);
    const row = await screen.findByRole('button', { name: /India vs Spain/ });

    fireEvent.click(row);

    expect(await screen.findByRole('heading', { name: 'India vs Spain' })).toBeInTheDocument();
  });

  it('goes from the list to the builder and back to a refreshed list after creating a comparison', async () => {
    stubFetch({
      countries: COUNTRIES,
      myComparisons: { items: [], total: 0, limit: 10, offset: 0 },
      myCalculations: { items: [], total: 0, limit: 10, offset: 0 },
      createComparison: DETAIL,
    });

    render(<ComparisonsView />);
    await screen.findByText("You haven't created any comparisons yet.");

    fireEvent.click(screen.getByRole('button', { name: 'New comparison' }));

    expect(await screen.findByRole('heading', { name: 'New comparison' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'My comparisons' })).toBeInTheDocument();
    });
  });

  it('shows a friendly error when a comparison fails to load', async () => {
    stubFetch({
      myComparisons: {
        items: [
          {
            id: 3,
            name: 'India vs Spain',
            comparison_currency: 'EUR',
            as_of_date: '2026-08-16',
            created_at: '2026-08-16T00:00:00Z',
            calculation_count: 2,
          },
        ],
        total: 1,
        limit: 10,
        offset: 0,
      },
      getComparison: {
        '3': {
          status: 404,
          body: { error: { code: 'comparison_not_found', message: 'Comparison not found' } },
        },
      },
    });

    render(<ComparisonsView />);
    const row = await screen.findByRole('button', { name: /India vs Spain/ });
    fireEvent.click(row);

    expect(
      await screen.findByText(/Could not load that comparison: Comparison not found/),
    ).toBeInTheDocument();
  });
});
