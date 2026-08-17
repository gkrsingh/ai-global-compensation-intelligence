import { useEffect, useState } from 'react';

import {
  ApiError,
  fetchMarketContext,
  type MarketContextOut,
  type MarketOccupationOut,
} from '../../api/client';
import { friendlyErrorLines } from '../../api/errors';

type PanelState =
  | { kind: 'loading' }
  | { kind: 'loaded'; context: MarketContextOut }
  | { kind: 'error'; error: ApiError };

export interface MarketContextPanelProps {
  jobFamilyId: number;
  countryCode: string;
}

const MATCH_QUALITY_LABEL: Record<string, string> = {
  close: 'Close match',
  broad: 'Broad match',
  poor: 'Poor match',
};

// Deliberately NOT the calculator's formatCurrency, for two reasons.
// Whole units only: OEWS annual figures are already rounded to the
// nearest dollar by BLS, and for many occupations they are derived
// (hourly x 2,080) rather than surveyed, so rendering "$135,980.00"
// would manufacture two digits of precision the source does not have.
// And keeping a separate formatter means a market estimate can never
// accidentally acquire the exact visual form of a computed figure.
function formatEstimate(amount: string | null, currencyCode: string): string {
  if (amount === null) return 'Not published';
  const value = Number(amount);
  if (Number.isNaN(value)) return 'Not published';
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currencyCode,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    // Intl throws on an unrecognized ISO 4217 code - fall back to plain
    // text rather than crash the panel over a formatting detail.
    return `${Math.round(value)} ${currencyCode}`;
  }
}

function OccupationCard({ occupation }: { occupation: MarketOccupationOut }) {
  const { distribution: d, currency_code: currency } = occupation;
  const quality = occupation.match_quality;

  // Every published point, in order, so the reader sees a spread rather
  // than one number. A percentile the source suppressed renders as "Not
  // published" - never as zero, and never quietly dropped, which would
  // make the distribution look more complete than it is.
  const points: { label: string; value: string | null }[] = [
    { label: '10th percentile', value: d.percentile_10 },
    { label: '25th percentile', value: d.percentile_25 },
    { label: 'Median', value: d.percentile_50 },
    { label: '75th percentile', value: d.percentile_75 },
    { label: '90th percentile', value: d.percentile_90 },
  ];

  return (
    <article className="market-occupation">
      <header className="market-occupation-header">
        <h4>{occupation.external_label}</h4>
        <span className={`market-match market-match-${quality}`}>
          {MATCH_QUALITY_LABEL[quality] ?? quality}
        </span>
      </header>

      <p className="market-match-note">{occupation.match_note}</p>

      <table className="market-distribution">
        <caption>
          Published wage distribution &mdash; {occupation.area_name},{' '}
          {occupation.reference_period_label}
        </caption>
        <tbody>
          {points.map((point) => (
            <tr key={point.label}>
              <th scope="row">{point.label}</th>
              <td className={point.value === null ? 'market-value-missing' : 'market-value'}>
                {formatEstimate(point.value, currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className="market-provenance">
        <div>
          <dt>Source</dt>
          <dd>
            <a href={occupation.source_url} target="_blank" rel="noopener noreferrer">
              {occupation.source_name}
            </a>
          </dd>
        </div>
        <div>
          <dt>Occupation code</dt>
          <dd>
            {occupation.taxonomy} {occupation.external_code}
          </dd>
        </div>
        <div>
          <dt>Collected</dt>
          <dd>
            {occupation.reference_period_label}
            {occupation.published_date ? ` (published ${occupation.published_date})` : ''}
          </dd>
        </div>
        <div>
          <dt>Geographic scope</dt>
          <dd>{occupation.area_name}</dd>
        </div>
        {occupation.employment_count !== null && (
          <div>
            <dt>Workers in estimate</dt>
            <dd>{occupation.employment_count.toLocaleString('en-US')}</dd>
          </div>
        )}
      </dl>

      <p className="market-methodology">{occupation.methodology_note}</p>
    </article>
  );
}

/**
 * Market context is a STATISTICAL ESTIMATE from a survey, not a computed
 * figure. That distinction is carried by construction here, not by a
 * disclaimer someone has to read: this panel has its own container and
 * accent (.market-context-panel in index.css), renders a distribution
 * rather than a single value, labels every figure as published rather
 * than calculated, and never appears inside the calculation's own
 * <dl>/results markup.
 */
export function MarketContextPanel({ jobFamilyId, countryCode }: MarketContextPanelProps) {
  const [state, setState] = useState<PanelState>({ kind: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: 'loading' });
    fetchMarketContext(jobFamilyId, countryCode)
      .then((context) => {
        if (!cancelled) setState({ kind: 'loaded', context });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError('unknown_error', 'An unexpected error occurred', null);
        setState({ kind: 'error', error: apiError });
      });
    return () => {
      cancelled = true;
    };
  }, [jobFamilyId, countryCode]);

  // Defensive `?? []`: this panel is embedded inside the results view, so
  // a malformed or partial payload must degrade to "nothing to show"
  // rather than throwing and taking the user's actual calculation down
  // with it. Market context is strictly supplementary - it should never
  // be able to break the deterministic result it sits beside.
  const occupations = state.kind === 'loaded' ? (state.context.occupations ?? []) : [];
  const excludesVariablePay = occupations.some((o) => o.excludes_variable_compensation);

  return (
    <section className="market-context-panel">
      <h3>Market context</h3>
      <p className="market-context-intro">
        Published government wage statistics for comparable occupations. These are survey{' '}
        <strong>estimates</strong>, not part of your calculation above &mdash; nothing here is
        computed from your figures.
      </p>

      {state.kind === 'loading' && <p>Loading market context…</p>}

      {state.kind === 'error' && (
        <div role="alert" className="error-banner">
          <ul>
            {friendlyErrorLines(state.error).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      {state.kind === 'loaded' && !state.context.available && (
        // Stated out loud rather than rendering nothing: silence would be
        // indistinguishable from a loading failure, and "we have no
        // citable source for this country" is a real, honest answer.
        <p className="market-unavailable" role="status">
          {state.context.unavailable_reason}
        </p>
      )}

      {state.kind === 'loaded' && state.context.available && occupations.length > 0 && (
        <>
          {excludesVariablePay && (
            // Deliberately ABOVE the numbers and styled as a warning, not
            // a footnote. For technology roles, bonus and equity are
            // routinely 20-50% of total compensation, so silently
            // comparing a total-comp offer against a base-pay-only market
            // figure would actively mislead someone mid-negotiation.
            <div className="market-warning" role="note">
              <strong>These figures exclude bonuses and equity.</strong> They cover base pay,
              commissions and production bonuses only &mdash; not annual bonuses, stock, or
              benefits. If your offer includes bonus or equity, compare those separately, and
              compare against your <strong>gross</strong> pay before tax, never your net.
            </div>
          )}

          {occupations.map((occupation) => (
            <OccupationCard key={occupation.external_code} occupation={occupation} />
          ))}

          <p className="market-context-disclaimer">
            No seniority or specialisation breakdown is published for these occupations &mdash;
            locate yourself within the range rather than reading any percentile as a level.
          </p>
        </>
      )}
    </section>
  );
}
