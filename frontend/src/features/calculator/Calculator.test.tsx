import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CalculationOut } from '../../api/client';
import { AuthProvider } from '../auth/AuthContext';
import { COUNTRIES, stubFetch } from '../../test/apiMocks';
import { Calculator } from './Calculator';

const CALCULATION: CalculationOut = {
  id: 1,
  compensation_input_id: 1,
  user_id: null,
  engine_version: '1.0.0',
  gross_amount: '50000.00',
  total_compensation_amount: '50000.00',
  tax_rule_set_id: null,
  total_tax_amount: null,
  net_amount: null,
  breakdown: {
    target_currency: 'EUR',
    as_of_date: '2026-08-15',
    rates_used: {},
    components: [
      {
        type: 'base',
        description: null,
        original_amount: '50000.00',
        original_currency: 'EUR',
        converted_amount: '50000.00',
        counts_toward_gross: true,
      },
    ],
    tax: null,
  },
  created_at: '2026-08-15T13:08:16.326507Z',
};

function renderCalculator() {
  return render(
    <AuthProvider>
      <Calculator />
    </AuthProvider>,
  );
}

async function fillAndSubmit() {
  await screen.findByDisplayValue('Spain (ES)');
  fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '50000' } });
  fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));
}

describe('Calculator', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders ResultsView with the real computed data after a successful submission', async () => {
    stubFetch({ countries: COUNTRIES, calculation: CALCULATION });

    renderCalculator();
    await fillAndSubmit();

    expect(await screen.findByText('Result')).toBeInTheDocument();
    const grossDt = screen.getByText('Gross compensation (cash only, before tax)');
    expect(grossDt.nextElementSibling?.textContent).toBe('€50,000.00');
  });

  it('shows the honest tracked-currencies note for a missing_exchange_rate error, without losing the form', async () => {
    stubFetch({
      countries: COUNTRIES,
      calculation: {
        status: 422,
        body: {
          error: {
            code: 'missing_exchange_rate',
            message: 'No exchange rate available for INR -> GBP',
            details: null,
          },
        },
      },
    });

    renderCalculator();
    await fillAndSubmit();

    expect(
      await screen.findByText('No exchange rate available for INR -> GBP'),
    ).toBeInTheDocument();
    expect(screen.getByText(/USD, INR, and EUR only/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Calculate' })).toBeInTheDocument();
  });

  it('returns to a fresh form when "New calculation" is clicked from results', async () => {
    stubFetch({ countries: COUNTRIES, calculation: CALCULATION });

    renderCalculator();
    await fillAndSubmit();
    await screen.findByText('Result');

    fireEvent.click(screen.getByRole('button', { name: 'New calculation' }));

    expect(await screen.findByRole('button', { name: 'Calculate' })).toBeInTheDocument();
  });

  it('still succeeds and shows a session-expired notice when the backend rejects a stale token', async () => {
    stubFetch({
      countries: COUNTRIES,
      calculation: CALCULATION,
      calculationAuthWarning: 'invalid_or_expired_token',
    });

    renderCalculator();
    await fillAndSubmit();

    expect(await screen.findByText('Result')).toBeInTheDocument();
    expect(screen.getByText(/Your session expired/)).toBeInTheDocument();
  });
});
