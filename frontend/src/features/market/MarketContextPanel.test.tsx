import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import type {
  MarketContextOut,
  MarketEntryOut,
  MarketOccupationOut,
  MarketSourceOut,
} from '../../api/client';
import { stubFetch } from '../../test/apiMocks';
import { MarketContextPanel } from './MarketContextPanel';

function entry(overrides: Partial<MarketEntryOut> = {}): MarketEntryOut {
  return {
    experience_band_label: null,
    experience_min_years: null,
    experience_max_years: null,
    sample_size: 1484,
    employment_count: null,
    distribution: {
      percentile_10: '80000.00',
      percentile_25: '104000.00',
      percentile_50: '140000.00',
      percentile_75: '180000.00',
      percentile_90: '225000.00',
      mean_value: '154292.00',
    },
    suppressed: false,
    ...overrides,
  };
}

function occupation(overrides: Partial<MarketOccupationOut> = {}): MarketOccupationOut {
  return {
    taxonomy: 'SO-DEVTYPE-2025',
    external_code: 'Developer, full-stack',
    external_label: 'Developer, full-stack',
    match_quality: 'close',
    match_note: 'Respondents who identify as full-stack developers.',
    geographic_scope: 'national',
    area_name: 'National',
    currency_code: 'USD',
    entries: [entry()],
    ...overrides,
  };
}

function surveySource(overrides: Partial<MarketSourceOut> = {}): MarketSourceOut {
  return {
    source_key: 'stackoverflow_survey',
    source_name: 'Stack Overflow Annual Developer Survey 2025',
    source_url: 'https://survey.stackoverflow.co/2025/',
    reference_period_label: '2025 survey',
    published_date: null,
    methodology_note: 'Aggregated from public results, licensed ODbL 1.0.',
    excludes_variable_compensation: false,
    wage_definition_note: 'Total annual compensation as reported by the respondent.',
    representativeness_note: null,
    occupations: [occupation()],
    ...overrides,
  };
}

function blsSource(overrides: Partial<MarketSourceOut> = {}): MarketSourceOut {
  return {
    source_key: 'bls_oews',
    source_name: 'US Bureau of Labor Statistics - OEWS',
    source_url: 'https://www.bls.gov/oes/current/oes_nat.htm',
    reference_period_label: 'May 2025',
    published_date: '2026-05-15',
    methodology_note: 'Semi-annual mail survey; self-employed excluded.',
    excludes_variable_compensation: true,
    wage_definition_note: 'Straight-time gross pay; excludes equity.',
    representativeness_note: null,
    occupations: [
      occupation({
        taxonomy: 'SOC-2018',
        external_code: '151252',
        external_label: 'Software Developers',
        match_note: 'Closest published match for software engineering roles.',
        entries: [
          entry({
            sample_size: null,
            employment_count: 1687890,
            distribution: {
              percentile_10: '82460.00',
              percentile_25: '105210.00',
              percentile_50: '135980.00',
              percentile_75: '171980.00',
              percentile_90: '214670.00',
              mean_value: '148100.00',
            },
          }),
        ],
      }),
    ],
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
    sources: [surveySource()],
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

    await waitFor(() => expect(screen.getByText('$140,000')).toBeInTheDocument());
    expect(screen.getByText('$80,000')).toBeInTheDocument();
    expect(screen.getByText('$104,000')).toBeInTheDocument();
    expect(screen.getByText('$180,000')).toBeInTheDocument();
    expect(screen.getByText('$225,000')).toBeInTheDocument();
  });

  it('shows both sources separately and says they are not combined', async () => {
    stubFetch({ marketContext: context({ sources: [blsSource(), surveySource()] }) });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);

    // Both sources' own medians are present and attributed - never
    // averaged into one figure.
    await waitFor(() => expect(screen.getByText('$135,980')).toBeInTheDocument());
    expect(screen.getByText('$140,000')).toBeInTheDocument();
    expect(screen.getByText('US Bureau of Labor Statistics - OEWS')).toBeInTheDocument();
    expect(screen.getByText('Stack Overflow Annual Developer Survey 2025')).toBeInTheDocument();
    // The midpoint of the two medians must never appear.
    expect(screen.queryByText('$137,990')).not.toBeInTheDocument();
    expect(screen.getByText(/never combined or averaged/i)).toBeInTheDocument();
  });

  it('renders the India representativeness caveat as a prominent banner', async () => {
    const note =
      'Read these India figures with particular care. The respondents skew heavily toward ' +
      'product-company and globally-connected developers.';
    stubFetch({
      marketContext: context({
        country_code: 'IN',
        sources: [surveySource({ representativeness_note: note })],
      }),
    });

    render(<MarketContextPanel jobFamilyId={1} countryCode="IN" />);

    // A note role (banner), not buried prose - and it must appear ABOVE
    // the figures it qualifies.
    const banners = await screen.findAllByRole('note');
    const repBanner = banners.find((b) => /particular care/i.test(b.textContent ?? ''));
    expect(repBanner).toBeDefined();
    expect(repBanner).toHaveTextContent(/product-company and globally-connected/i);
    expect(repBanner).toHaveClass('market-warning-representativeness');
  });

  it('shows an insufficient-sample row instead of omitting a thin cell', async () => {
    stubFetch({
      marketContext: context({
        sources: [
          surveySource({
            occupations: [
              occupation({
                entries: [
                  entry({
                    experience_band_label: '0-2 yrs',
                    experience_min_years: 0,
                    experience_max_years: 2,
                    sample_size: 12,
                    suppressed: true,
                    distribution: {
                      percentile_10: null,
                      percentile_25: null,
                      percentile_50: null,
                      percentile_75: null,
                      percentile_90: null,
                      mean_value: null,
                    },
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
    });

    render(<MarketContextPanel jobFamilyId={1} countryCode="ES" />);

    // Visible absence with its reason and count - not a silent omission.
    expect(await screen.findByText(/insufficient sample/i)).toBeInTheDocument();
    expect(screen.getByText(/only 12 responses/i)).toBeInTheDocument();
    expect(screen.queryByText('$0')).not.toBeInTheDocument();
  });

  it('labels experience bands as years, never as seniority titles', async () => {
    stubFetch({
      marketContext: context({
        sources: [
          surveySource({
            occupations: [
              occupation({
                entries: [
                  entry({
                    experience_band_label: '6-10 yrs',
                    experience_min_years: 6,
                    experience_max_years: 10,
                    sample_size: 248,
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
    });

    render(<MarketContextPanel jobFamilyId={1} countryCode="IN" />);

    expect(await screen.findByText(/6-10 yrs/)).toBeInTheDocument();
    // No source publishes a years-to-title mapping, so none is implied.
    expect(screen.queryByText(/\bSenior\b/)).not.toBeInTheDocument();
    expect(screen.getByText(/not job levels/i)).toBeInTheDocument();
  });

  it('shows the sample size behind a survey figure', async () => {
    stubFetch({ marketContext: context() });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);

    expect(await screen.findByText(/n=1,484/)).toBeInTheDocument();
  });

  it('still warns that BLS figures exclude bonuses and equity', async () => {
    stubFetch({ marketContext: context({ sources: [blsSource()] }) });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);

    const banner = await screen.findByRole('note');
    expect(banner).toHaveTextContent(/exclude bonuses and equity/i);
    expect(banner).toHaveTextContent(/gross/i);
  });

  it('states the match quality prominently, including for a poor match', async () => {
    stubFetch({
      marketContext: context({
        sources: [
          surveySource({
            occupations: [
              occupation({
                match_quality: 'poor',
                match_note: 'SOC-2018 has no product management occupation at all.',
              }),
            ],
          }),
        ],
      }),
    });

    render(<MarketContextPanel jobFamilyId={2} countryCode="US" />);

    expect(await screen.findByText('Poor match')).toBeInTheDocument();
  });

  it('states the reason out loud when no data is available', async () => {
    stubFetch({
      marketContext: context({
        available: false,
        unavailable_reason: 'No market compensation data is available for this country.',
        sources: [],
      }),
    });

    render(<MarketContextPanel jobFamilyId={1} countryCode="ZZ" />);

    expect(
      await screen.findByText(/no market compensation data is available/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('never presents the estimates as part of the calculation', async () => {
    stubFetch({ marketContext: context() });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);

    await screen.findByText('$140,000');
    expect(screen.getByText(/not part of your calculation/i)).toBeInTheDocument();
  });

  it('attributes each figure to its own source section', async () => {
    stubFetch({ marketContext: context({ sources: [blsSource(), surveySource()] }) });

    render(<MarketContextPanel jobFamilyId={1} countryCode="US" />);
    await screen.findByText('$135,980');

    // The BLS median must live inside the BLS section, not float free
    // where it could be read as belonging to either source.
    const blsHeading = screen.getByText('US Bureau of Labor Statistics - OEWS');
    const blsSection = blsHeading.closest('section');
    expect(blsSection).not.toBeNull();
    expect(within(blsSection!).getByText('$135,980')).toBeInTheDocument();
    expect(within(blsSection!).queryByText('$140,000')).not.toBeInTheDocument();
  });
});
