import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { CalculationOut, ComparisonDetailOut } from '../../api/client';
import { ComparisonResultView } from './ComparisonResultView';

function calculation(id: number, currency: string, gross: string): CalculationOut {
  return {
    id,
    compensation_input_id: id,
    user_id: 1,
    engine_version: '1.0.0',
    gross_amount: gross,
    total_compensation_amount: gross,
    tax_rule_set_id: null,
    total_tax_amount: null,
    net_amount: null,
    breakdown: {
      target_currency: currency,
      as_of_date: '2026-08-16',
      rates_used: {},
      components: [],
      tax: null,
    },
    created_at: '2026-08-16T00:00:00Z',
  };
}

// Mirrors the hand-verified US $150k vs $100k comparison from
// test_comparison_api.py::test_create_comparison_hand_verified_gap_analysis
// - the same figures, so this doubles as a frontend-side confirmation
// that the rendering doesn't silently mangle the backend's numbers.
const COMPARISON: ComparisonDetailOut = {
  id: 7,
  name: 'US offers',
  comparison_currency: 'USD',
  as_of_date: '2026-08-16',
  created_at: '2026-08-16T00:00:00Z',
  entries: [
    {
      calculation_id: 1,
      source_currency: 'USD',
      rate_used: null,
      gross_amount: '150000.00',
      total_compensation_amount: '150000.00',
      total_tax_amount: '36209.00',
      net_amount: '113791.00',
    },
    {
      calculation_id: 2,
      source_currency: 'USD',
      rate_used: null,
      gross_amount: '100000.00',
      total_compensation_amount: '100000.00',
      total_tax_amount: '20820.00',
      net_amount: '79180.00',
    },
  ],
  gap_analysis: {
    gross_amount: {
      leader_calculation_id: 1,
      entries: [
        { calculation_id: 1, gap_absolute: '0.00', gap_percent: '0.00' },
        { calculation_id: 2, gap_absolute: '50000.00', gap_percent: '50.00' },
      ],
    },
    total_compensation_amount: {
      leader_calculation_id: 1,
      entries: [
        { calculation_id: 1, gap_absolute: '0.00', gap_percent: '0.00' },
        { calculation_id: 2, gap_absolute: '50000.00', gap_percent: '50.00' },
      ],
    },
    net_amount: {
      leader_calculation_id: 1,
      entries: [
        { calculation_id: 1, gap_absolute: '0.00', gap_percent: '0.00' },
        { calculation_id: 2, gap_absolute: '34611.00', gap_percent: '43.71' },
      ],
    },
  },
  calculations: [calculation(1, 'USD', '150000.00'), calculation(2, 'USD', '100000.00')],
};

describe('ComparisonResultView', () => {
  it('renders the side-by-side table with converted figures', () => {
    render(<ComparisonResultView comparison={COMPARISON} onBack={vi.fn()} />);

    expect(screen.getByText('US offers')).toBeInTheDocument();
    expect(screen.getAllByText('$150,000.00').length).toBeGreaterThan(0);
    expect(screen.getAllByText('$100,000.00').length).toBeGreaterThan(0);
  });

  it('shows the correct leader and hand-verified gap figures for each metric', () => {
    render(<ComparisonResultView comparison={COMPARISON} onBack={vi.fn()} />);

    expect(screen.getByText(/Gross compensation — Offer 1 is ahead/)).toBeInTheDocument();
    expect(screen.getByText(/Net compensation — Offer 1 is ahead/)).toBeInTheDocument();
    expect(screen.getByText('$34,611.00')).toBeInTheDocument();
    expect(screen.getByText('43.71%')).toBeInTheDocument();
  });

  it('reuses ResultsView to render each offer\'s full per-offer breakdown, without its "New calculation" button', () => {
    render(<ComparisonResultView comparison={COMPARISON} onBack={vi.fn()} />);

    expect(screen.getByRole('heading', { name: 'Offer 1' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Offer 2' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New calculation' })).not.toBeInTheDocument();
  });

  it('calls onBack when "Back to comparisons" is clicked', () => {
    const onBack = vi.fn();
    render(<ComparisonResultView comparison={COMPARISON} onBack={onBack} />);

    fireEvent.click(screen.getByRole('button', { name: 'Back to comparisons' }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('shows an honest note instead of a gap ranking when a metric is unavailable for every offer', () => {
    const comparisonWithoutNet: ComparisonDetailOut = {
      ...COMPARISON,
      gap_analysis: { ...COMPARISON.gap_analysis, net_amount: null },
    };

    render(<ComparisonResultView comparison={comparisonWithoutNet} onBack={vi.fn()} />);

    expect(screen.getByText(/Net compensation: not available for every offer/)).toBeInTheDocument();
  });
});
