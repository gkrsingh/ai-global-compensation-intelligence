import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { COUNTRIES, stubFetch } from '../../test/apiMocks';
import { CompensationForm } from './CompensationForm';

describe('CompensationForm', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads countries and defaults target currency + row currency to the first country', async () => {
    stubFetch({ countries: COUNTRIES });

    render(<CompensationForm onSubmit={vi.fn()} />);

    expect(await screen.findByDisplayValue('Spain (ES)')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Euro (EUR)')).toBeInTheDocument();
  });

  it('blocks submission and shows a message when the amount is empty', async () => {
    stubFetch({ countries: COUNTRIES });
    const onSubmit = vi.fn();

    render(<CompensationForm onSubmit={onSubmit} />);
    await screen.findByDisplayValue('Spain (ES)');

    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    expect(await screen.findByText('Component 1: enter an amount.')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('blocks submission and shows a message for a negative amount', async () => {
    stubFetch({ countries: COUNTRIES });
    const onSubmit = vi.fn();

    render(<CompensationForm onSubmit={onSubmit} />);
    await screen.findByDisplayValue('Spain (ES)');

    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '-100' } });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    expect(await screen.findByText('Component 1: amount cannot be negative.')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits the expected payload for a valid single-component entry', async () => {
    stubFetch({ countries: COUNTRIES });
    const onSubmit = vi.fn();

    render(<CompensationForm onSubmit={onSubmit} />);
    await screen.findByDisplayValue('Spain (ES)');

    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '50000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      country_code: 'ES',
      target_currency_code: 'EUR',
      regime: null,
      // Null when the user picks no job family, which stays the default.
      // The calculator must keep working without one - a family only
      // unlocks the market context panel, it never affects a computed
      // figure.
      job_family_id: null,
      components: [
        { component_type: 'base', amount: '50000', currency_code: 'EUR', description: null },
      ],
    });
  });

  it('adds and removes component rows, disabling remove at exactly one row', async () => {
    stubFetch({ countries: COUNTRIES });

    render(<CompensationForm onSubmit={vi.fn()} />);
    await screen.findByDisplayValue('Spain (ES)');

    expect(screen.getByRole('button', { name: 'Remove component 1' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Add component' }));
    expect(screen.getAllByLabelText('Amount')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Remove component 1' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Remove component 2' }));
    expect(screen.getAllByLabelText('Amount')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Remove component 1' })).toBeDisabled();
  });

  it('re-defaults the target currency when the country changes', async () => {
    stubFetch({ countries: COUNTRIES });

    render(<CompensationForm onSubmit={vi.fn()} />);
    await screen.findByDisplayValue('Spain (ES)');

    fireEvent.change(screen.getByLabelText('Country'), { target: { value: 'IN' } });

    expect(await screen.findByDisplayValue('Indian Rupee (INR)')).toBeInTheDocument();
  });

  it('shows a regime selector only for a country with more than one regime, defaulted to the first', async () => {
    stubFetch({
      countries: COUNTRIES,
      taxRuleSets: {
        IN: [
          {
            id: 1,
            name: 'India new regime',
            regime: 'new',
            filing_status: null,
            standard_deduction: '75000',
            effective_date: '2026-01-01',
            end_date: null,
            source_url: null,
            currency: { code: 'INR', name: 'Indian Rupee', symbol: '₹' },
            tax_brackets: [],
          },
          {
            id: 2,
            name: 'India old regime',
            regime: 'old',
            filing_status: null,
            standard_deduction: '50000',
            effective_date: '2026-01-01',
            end_date: null,
            source_url: null,
            currency: { code: 'INR', name: 'Indian Rupee', symbol: '₹' },
            tax_brackets: [],
          },
        ],
        ES: [],
      },
    });

    render(<CompensationForm onSubmit={vi.fn()} />);
    await screen.findByDisplayValue('Spain (ES)');

    expect(screen.queryByLabelText('Tax regime')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Country'), { target: { value: 'IN' } });

    expect(await screen.findByDisplayValue('New regime')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Old regime' })).toBeInTheDocument();
  });
});
