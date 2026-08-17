import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { MarketContextOut, MarketOccupationOut } from '../../api/client';
import { stubFetch } from '../../test/apiMocks';
import { MarketContextPanel } from './MarketContextPanel';

function occupation(overrides: Partial<MarketOccupationOut> = {}): MarketOccupationOut {
  return {
    taxonomy: 'SOC-2018',
    external_code: '151252',
    external_label: 'Software Developers',
    match_quality: 'close',
    match_note: 'Closest published match for software engineering roles.',
    geographic_scope: 'national',
    area_name: 'National',
    currency_code: 'USD',
    distribution: {
      percentile_10: '82460.00',
      percentile_25: '105210.00',
      percentile_50: '135980.00',
      percentile_75: '171980.00',
      percentile_90: '214670.00',
      mean_value: '148100.00',
    },
    employment_count: 1687890,
    reference_period_label: 'May 2025',
    published_date: '2026-05-15',
    source_name: 'US Bureau of Labor Statistics - OEWS',
    source_url: 'https://www.bls.gov/oes/current/oes_nat.htm',
    methodology_note: 'Semi-annual mail survey; self-employed excluded.',
    excludes_variable_compensation: true,
    wage_definition_note: 'Straight-time gross pay; excludes equity and non-production bonuses.',
    ...overrides,
  };
}

function context(overrides: Partial<MarketContextOut> = {}): MarketContextOut {
  return {
    country_code: 'US',
    job_family_id: 1,
    job_family_name: 'Software Engineering',
    available: true,
    unavailable_reason: null,
    occupations: [occupation()],
    ...overrides,
  };
}

describe('MarketContextPanel', () => {
  beforeEach(() => {
    stubFetch({});
  });

  it('shows the full distribution rather than a single headline number', async () => {
    stubFetch({ marketContext: context() });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);

    // Every published percentile is visible - a lone median would invite
    // exactly the false-precision reading this panel exists to prevent.
    await waitFor(() => expect(screen.getByText('$135,980')).toBeInTheDocument());
    expect(screen.getByText('$82,460')).toBeInTheDocument();
    expect(screen.getByText('$105,210')).toBeInTheDocument();
    expect(screen.getByText('$171,980')).toBeInTheDocument();
    expect(screen.getByText('$214,670')).toBeInTheDocument();
    expect(screen.getByText('10th percentile')).toBeInTheDocument();
    expect(screen.getByText('90th percentile')).toBeInTheDocument();
  });

  it('warns loudly that the figures exclude bonuses and equity', async () => {
    stubFetch({ marketContext: context() });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);

    // The single most misleading thing about OEWS for tech compensation:
    // it must be stated as a warning, not buried in a footnote.
    const warning = await screen.findByRole('note');
    expect(warning).toHaveTextContent(/exclude bonuses and equity/i);
    expect(warning).toHaveTextContent(/gross/i);
  });

  it('states the match quality prominently, including for a poor match', async () => {
    stubFetch({
      marketContext: context({
        job_family_name: 'Product Management',
        occupations: [
          occupation({
            external_code: '131082',
            external_label: 'Project Management Specialists',
            match_quality: 'poor',
            match_note: 'SOC-2018 has no product management occupation at all.',
          }),
        ],
      }),
    });

    render(<MarketContextPanel jobFamilyId={2} countryCode="US" />);

    // Text, not just colour - the signal has to survive greyscale.
    expect(await screen.findByText('Poor match')).toBeInTheDocument();
    expect(screen.getByText(/no product management occupation/i)).toBeInTheDocument();
  });

  it('shows provenance: source, collection period and geographic scope', async () => {
    stubFetch({ marketContext: context() });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);

    const sourceLink = await screen.findByText('US Bureau of Labor Statistics - OEWS');
    expect(sourceLink).toBeInTheDocument();
    expect(sourceLink.closest('a')).toHaveAttribute(
      'href',
      'https://www.bls.gov/oes/current/oes_nat.htm',
    );
    // Appears in both the table caption and the provenance list, on
    // purpose - the vintage should be visible without scrolling to the
    // fine print, so more than one hit is correct here.
    expect(screen.getAllByText(/May 2025/).length).toBeGreaterThan(0);
    expect(screen.getByText(/published 2026-05-15/)).toBeInTheDocument();
    expect(screen.getByText('SOC-2018 151252')).toBeInTheDocument();
    expect(screen.getByText('Geographic scope')).toBeInTheDocument();
  });

  it('renders a suppressed percentile as not published, never as zero', async () => {
    stubFetch({
      marketContext: context({
        occupations: [
          occupation({
            distribution: {
              percentile_10: null,
              percentile_25: null,
              percentile_50: '135980.00',
              percentile_75: null,
              percentile_90: null,
              mean_value: null,
            },
          }),
        ],
      }),
    });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);

    await waitFor(() => expect(screen.getByText('$135,980')).toBeInTheDocument());
    expect(screen.getAllByText('Not published').length).toBe(4);
    // A wage of zero is a claim nobody made.
    expect(screen.queryByText('$0')).not.toBeInTheDocument();
  });

  it('states the reason out loud when no data is available', async () => {
    stubFetch({
      marketContext: context({
        country_code: 'IN',
        available: false,
        unavailable_reason: 'No market compensation data is available for this country.',
        occupations: [],
      }),
    });

    render(<MarketContextPanel jobFamilyId={1} countryCode="IN" />);

    // Rendering nothing would be indistinguishable from a loading bug.
    expect(
      await screen.findByText(/no market compensation data is available/i),
    ).toBeInTheDocument();
    // And the bonus/equity warning must NOT appear when there are no
    // figures for it to qualify.
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('never presents the estimates as part of the calculation', async () => {
    stubFetch({ marketContext: context() });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);

    await screen.findByText('$135,980');
    // The intro must say plainly that these are survey estimates and not
    // part of the calculation above.
    expect(screen.getByText(/not part of your calculation/i)).toBeInTheDocument();
    // And that no seniority breakdown exists, so a percentile is never
    // read as a level.
    expect(screen.getByText(/no seniority or specialisation breakdown/i)).toBeInTheDocument();
  });
});
