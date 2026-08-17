import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { CalculationOut } from '../../api/client';
import { stubFetch } from '../../test/apiMocks';
import { ResultsView } from './ResultsView';

const US_CALCULATION: CalculationOut = {
  id: 2,
  compensation_input_id: 4,
  country_code: 'US',
  job_family_id: null,
  user_id: null,
  engine_version: '1.0.0',
  gross_amount: '150000.00',
  total_compensation_amount: '150000.00',
  tax_rule_set_id: 2,
  total_tax_amount: '36209.00',
  net_amount: '113791.00',
  breakdown: {
    target_currency: 'USD',
    as_of_date: '2026-08-15',
    rates_used: {},
    components: [
      {
        type: 'base',
        description: null,
        original_amount: '150000.00',
        original_currency: 'USD',
        converted_amount: '150000.00',
        counts_toward_gross: true,
      },
    ],
    tax: {
      rule_set_id: 2,
      rule_set_name: 'US Federal Income Tax — Single Filer (TY2026)',
      currency: 'USD',
      standard_deduction: '16100.00',
      components: [
        {
          component: 'social_security',
          taxable_base: '150000.00',
          total_tax: '9300.00',
          brackets: [
            {
              lower_bound: '0.00',
              upper_bound: '184500.00',
              rate: '0.06200',
              taxable_amount: '150000.00',
              tax_amount: '9300.00',
            },
          ],
        },
        {
          component: 'income_tax',
          taxable_base: '133900.00',
          total_tax: '24734.00',
          brackets: [
            {
              lower_bound: '0.00',
              upper_bound: '12400.00',
              rate: '0.10000',
              taxable_amount: '12400.00',
              tax_amount: '1240.00',
            },
            {
              lower_bound: '12400.00',
              upper_bound: '50400.00',
              rate: '0.12000',
              taxable_amount: '38000.00',
              tax_amount: '4560.00',
            },
          ],
        },
      ],
    },
  },
  created_at: '2026-08-15T13:08:16.326507Z',
};

const NO_TAX_RULE_SET_CALCULATION: CalculationOut = {
  id: 3,
  compensation_input_id: 5,
  country_code: 'US',
  job_family_id: null,
  user_id: null,
  engine_version: '1.0.0',
  gross_amount: '50000.00',
  total_compensation_amount: '50000.00',
  tax_rule_set_id: null,
  total_tax_amount: null,
  net_amount: null,
  breakdown: {
    target_currency: 'EUR',
    as_of_date: '2020-01-01',
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

const INDIA_TO_EUR_CALCULATION: CalculationOut = {
  id: 4,
  compensation_input_id: 6,
  country_code: 'US',
  job_family_id: null,
  user_id: null,
  engine_version: '1.0.0',
  gross_amount: '15000.00',
  total_compensation_amount: '15000.00',
  tax_rule_set_id: 5,
  total_tax_amount: '937.50',
  net_amount: '14062.50',
  breakdown: {
    target_currency: 'EUR',
    as_of_date: '2026-08-15',
    rates_used: { 'INR->EUR': '0.01000000' },
    components: [
      {
        type: 'base',
        description: null,
        original_amount: '1500000.00',
        original_currency: 'INR',
        converted_amount: '15000.00',
        counts_toward_gross: true,
      },
    ],
    // The tax law's own currency (INR) differs from target_currency (EUR)
    // - the scenario the Phase 6 tax-currency-mismatch fix exists for.
    tax: {
      rule_set_id: 5,
      rule_set_name: 'India New Regime Income Tax (FY2026-27)',
      currency: 'INR',
      standard_deduction: '75000.00',
      components: [
        {
          component: 'income_tax',
          taxable_base: '1425000.00',
          total_tax: '93750.00',
          brackets: [
            {
              lower_bound: '400000.00',
              upper_bound: '800000.00',
              rate: '0.05000',
              taxable_amount: '400000.00',
              tax_amount: '20000.00',
            },
          ],
        },
      ],
    },
  },
  created_at: '2026-08-15T13:08:16.326507Z',
};

describe('ResultsView', () => {
  it('renders the gross/total/tax/net summary with unambiguous labels', () => {
    render(<ResultsView calculation={US_CALCULATION} onReset={vi.fn()} />);

    // gross_amount equals total_compensation_amount and the sole
    // component's amount in this fixture, so the formatted figure appears
    // more than once on the page - relate each label to its own value via
    // the dt/dd pairing ResultsView renders, rather than a bare text match.
    const grossDt = screen.getByText('Gross compensation (cash only, before tax)');
    expect(grossDt.nextElementSibling?.textContent).toBe('$150,000.00');

    const taxDt = screen.getByText('Total tax');
    expect(taxDt.nextElementSibling?.textContent).toBe('$36,209.00');

    const netDt = screen.getByText('Net compensation (cash only, after tax)');
    expect(netDt.nextElementSibling?.textContent).toBe('$113,791.00');
  });

  it('renders the compensation components table', () => {
    render(<ResultsView calculation={US_CALCULATION} onReset={vi.fn()} />);

    expect(screen.getByText('Base salary')).toBeInTheDocument();
    const row = screen.getByText('Base salary').closest('tr');
    expect(row).not.toBeNull();
    expect(row!.textContent).toContain('Yes');
  });

  it('renders per-tax-component breakdown with bracket detail', () => {
    render(<ResultsView calculation={US_CALCULATION} onReset={vi.fn()} />);

    expect(screen.getByText(/Social security/)).toBeInTheDocument();
    expect(screen.getByText(/Income tax/)).toBeInTheDocument();
    expect(screen.getByText('10.00%')).toBeInTheDocument();
    expect(screen.getByText('$4,560.00')).toBeInTheDocument();
    expect(screen.getByText(/Standard deduction applied to income tax/)).toBeInTheDocument();
  });

  it('shows a plain-language note instead of blank figures when no tax rule set applies', () => {
    render(<ResultsView calculation={NO_TAX_RULE_SET_CALCULATION} onReset={vi.fn()} />);

    expect(screen.queryByText('Total tax')).not.toBeInTheDocument();
    expect(screen.queryByText(/Net compensation/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/No applicable tax rule set was found for this country and date/),
    ).toBeInTheDocument();
    // The figures that don't depend on tax are still shown and accurate.
    const grossDt = screen.getByText('Gross compensation (cash only, before tax)');
    expect(grossDt.nextElementSibling?.textContent).toBe('€50,000.00');
  });

  it("shows tax breakdown figures in the tax law's own currency, not target_currency, when they differ", () => {
    render(<ResultsView calculation={INDIA_TO_EUR_CALCULATION} onReset={vi.fn()} />);

    // Top-level summary figures use target_currency (EUR).
    const grossDt = screen.getByText('Gross compensation (cash only, before tax)');
    expect(grossDt.nextElementSibling?.textContent).toBe('€15,000.00');
    const taxDt = screen.getByText('Total tax');
    expect(taxDt.nextElementSibling?.textContent).toBe('€937.50');

    // Tax breakdown figures use the tax law's own currency (INR), not EUR.
    expect(screen.getByText(/Tax figures below are shown in INR/)).toBeInTheDocument();
    expect(screen.getByText(/₹93,750\.00/)).toBeInTheDocument();
    expect(screen.getByText(/Taxable base/).textContent).toContain('₹1,425,000.00');
  });

  it('calls onReset when "New calculation" is clicked', () => {
    const onReset = vi.fn();
    render(<ResultsView calculation={US_CALCULATION} onReset={onReset} />);

    fireEvent.click(screen.getByRole('button', { name: 'New calculation' }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('shows a "saved to your history" note only when the calculation is tagged to a user', () => {
    const { rerender } = render(
      <ResultsView calculation={{ ...US_CALCULATION, user_id: null }} onReset={vi.fn()} />,
    );
    expect(screen.queryByText('Saved to your history.')).not.toBeInTheDocument();

    rerender(<ResultsView calculation={{ ...US_CALCULATION, user_id: 7 }} onReset={vi.fn()} />);
    expect(screen.getByText('Saved to your history.')).toBeInTheDocument();
  });

  it('does not show an AI insight panel for an anonymous (unsaved) calculation', () => {
    render(<ResultsView calculation={{ ...US_CALCULATION, user_id: null }} onReset={vi.fn()} />);

    expect(screen.queryByRole('button', { name: 'Generate AI insight' })).not.toBeInTheDocument();
  });

  it('shows an AI insight panel once the calculation is saved to history', () => {
    render(<ResultsView calculation={{ ...US_CALCULATION, user_id: 7 }} onReset={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Generate AI insight' })).toBeInTheDocument();
  });

  it('suppresses the AI insight panel in embedded, read-only views (showActions=false)', () => {
    render(
      <ResultsView
        calculation={{ ...US_CALCULATION, user_id: 7 }}
        onReset={vi.fn()}
        showActions={false}
      />,
    );

    // A comparison's own AIInsightPanel (targeting the comparison as a
    // whole) already covers this - each per-offer breakdown embedded
    // inside it doesn't need a second, narrower one of its own.
    expect(screen.queryByRole('button', { name: 'Generate AI insight' })).not.toBeInTheDocument();
  });

  it('omits market context entirely when the calculation has no job family', () => {
    // The calculator does not require a job family, and there is no
    // honest way to map a missing one onto a published occupation -
    // so the panel is absent rather than guessing or rendering empty.
    render(
      <ResultsView
        calculation={{ ...US_CALCULATION, job_family_id: null }}
        onReset={vi.fn()}
      />,
    );

    expect(screen.queryByText('Market context')).not.toBeInTheDocument();
  });

  it('shows market context when the calculation has a job family', async () => {
    stubFetch({
      marketContext: {
        country_code: 'US',
        job_family_id: 1,
        job_family_name: 'Software Engineering',
        available: false,
        unavailable_reason: 'No wage data has been ingested yet.',
        occupations: [],
      },
    });

    render(
      <ResultsView calculation={{ ...US_CALCULATION, job_family_id: 1 }} onReset={vi.fn()} />,
    );

    expect(await screen.findByText('Market context')).toBeInTheDocument();
  });
});
