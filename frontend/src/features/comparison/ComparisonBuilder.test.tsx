import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CalculationOut, ComparisonDetailOut } from '../../api/client';
import { COUNTRIES, stubFetch } from '../../test/apiMocks';
import { ComparisonBuilder } from './ComparisonBuilder';

function calculation(id: number, grossAmount: string): CalculationOut {
  return {
    id,
    compensation_input_id: id,
    country_code: 'US',
    job_family_id: null,
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

const RESULT: ComparisonDetailOut = {
  id: 9,
  name: 'built comparison',
  comparison_currency: 'USD',
  as_of_date: '2026-08-16',
  created_at: '2026-08-16T00:00:00Z',
  entries: [],
  gap_analysis: { gross_amount: null, total_compensation_amount: null, net_amount: null },
  calculations: [],
};

describe('ComparisonBuilder', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('disables submit until 2+ calculations are selected', async () => {
    stubFetch({
      countries: COUNTRIES,
      myCalculations: {
        items: [calculation(1, '1000.00'), calculation(2, '2000.00')],
        total: 2,
        limit: 10,
        offset: 0,
      },
    });

    render(<ComparisonBuilder onCreated={vi.fn()} onCancel={vi.fn()} />);
    await screen.findByText(/Gross: \$1,000\.00/);

    fireEvent.change(screen.getByLabelText('Comparison name'), {
      target: { value: 'my comparison' },
    });
    const submit = screen.getByRole('button', { name: 'Create comparison' });
    expect(submit).toBeDisabled();

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);
    expect(submit).toBeDisabled();

    fireEvent.click(checkboxes[1]);
    expect(submit).not.toBeDisabled();
  });

  it('submits the selected calculation ids and the chosen currency, then calls onCreated', async () => {
    const fetchSpy = stubFetch({
      countries: COUNTRIES,
      myCalculations: {
        items: [calculation(1, '1000.00'), calculation(2, '2000.00')],
        total: 2,
        limit: 10,
        offset: 0,
      },
      createComparison: RESULT,
    });

    const onCreated = vi.fn();
    render(<ComparisonBuilder onCreated={onCreated} onCancel={vi.fn()} />);
    await screen.findByText(/Gross: \$1,000\.00/);

    fireEvent.change(screen.getByLabelText('Comparison name'), {
      target: { value: 'my comparison' },
    });
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);

    fireEvent.click(screen.getByRole('button', { name: 'Create comparison' }));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(RESULT);
    });

    const postCall = fetchSpy.mock.calls.find(
      (call) => String(call[0]).endsWith('/comparisons') && call[1]?.method === 'POST',
    );
    expect(postCall).toBeDefined();
    const body = JSON.parse(String(postCall?.[1]?.body)) as {
      name: string;
      calculation_ids: number[];
      comparison_currency_code: string;
    };
    expect(body.name).toBe('my comparison');
    expect(body.calculation_ids.sort()).toEqual([1, 2]);
    expect(body.comparison_currency_code).toBe('EUR'); // COUNTRIES[0] is Spain/EUR
  });

  it('shows a friendly error and re-enables the form when creation fails', async () => {
    stubFetch({
      countries: COUNTRIES,
      myCalculations: {
        items: [calculation(1, '1000.00'), calculation(2, '2000.00')],
        total: 2,
        limit: 10,
        offset: 0,
      },
      createComparison: {
        status: 422,
        body: {
          error: {
            code: 'missing_exchange_rate',
            message: 'No exchange rate available for INR -> EUR',
            details: null,
          },
        },
      },
    });

    render(<ComparisonBuilder onCreated={vi.fn()} onCancel={vi.fn()} />);
    await screen.findByText(/Gross: \$1,000\.00/);

    fireEvent.change(screen.getByLabelText('Comparison name'), {
      target: { value: 'my comparison' },
    });
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    fireEvent.click(screen.getByRole('button', { name: 'Create comparison' }));

    expect(
      await screen.findByText('No exchange rate available for INR -> EUR'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create comparison' })).not.toBeDisabled();
  });

  it('calls onCancel when Cancel is clicked', async () => {
    stubFetch({
      countries: COUNTRIES,
      myCalculations: { items: [], total: 0, limit: 10, offset: 0 },
    });
    const onCancel = vi.fn();
    render(<ComparisonBuilder onCreated={vi.fn()} onCancel={onCancel} />);

    await screen.findByText(/nothing to compare/);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
