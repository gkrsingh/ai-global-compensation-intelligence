import { useEffect, useState } from 'react';

import {
  ApiError,
  fetchMarketContext,
  type MarketContextOut,
  type MarketEntryOut,
  type MarketOccupationOut,
  type MarketSourceOut,
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
// Whole units only: these figures are already rounded by their sources
// and, in the survey's case, converted between currencies, so cents
// would manufacture precision the data does not have. And keeping a
// separate formatter means a market estimate can never accidentally
// acquire the exact visual form of a computed figure.
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
    return `${Math.round(value)} ${currencyCode}`;
  }
}

function entryLabel(entry: MarketEntryOut): string {
  // Years as measured, never relabelled to a seniority title - no source
  // publishes that mapping.
  return entry.experience_band_label ?? 'All experience levels';
}

function DistributionRow({ entry, currency }: { entry: MarketEntryOut; currency: string }) {
  if (entry.suppressed) {
    return (
      <tr className="market-suppressed-row">
        <th scope="row">{entryLabel(entry)}</th>
        <td colSpan={5} className="market-value-missing">
          Insufficient sample
          {entry.sample_size !== null ? ` (only ${entry.sample_size} responses)` : ''} &mdash; not
          published
        </td>
      </tr>
    );
  }

  const d = entry.distribution;
  const cells = [
    d.percentile_10,
    d.percentile_25,
    d.percentile_50,
    d.percentile_75,
    d.percentile_90,
  ];

  return (
    <tr>
      <th scope="row">
        {entryLabel(entry)}
        {entry.sample_size !== null && (
          <span className="market-sample"> n={entry.sample_size.toLocaleString('en-US')}</span>
        )}
      </th>
      {cells.map((value, index) => (
        <td key={index} className={value === null ? 'market-value-missing' : 'market-value'}>
          {formatEstimate(value, currency)}
        </td>
      ))}
    </tr>
  );
}

function OccupationCard({ occupation }: { occupation: MarketOccupationOut }) {
  const quality = occupation.match_quality;

  return (
    <article className="market-occupation">
      <header className="market-occupation-header">
        <h5>{occupation.external_label}</h5>
        <span className={`market-match market-match-${quality}`}>
          {MATCH_QUALITY_LABEL[quality] ?? quality}
        </span>
      </header>

      <p className="market-match-note">{occupation.match_note}</p>

      <div className="market-table-scroll">
        <table className="market-distribution">
          <caption>Published wage distribution &mdash; {occupation.area_name}</caption>
          <thead>
            <tr>
              <th scope="col">Experience</th>
              <th scope="col">10th</th>
              <th scope="col">25th</th>
              <th scope="col">Median</th>
              <th scope="col">75th</th>
              <th scope="col">90th</th>
            </tr>
          </thead>
          <tbody>
            {occupation.entries.map((entry) => (
              <DistributionRow
                key={entry.experience_band_label ?? 'all'}
                entry={entry}
                currency={occupation.currency_code}
              />
            ))}
          </tbody>
        </table>
      </div>

      <p className="market-occupation-code">
        {occupation.taxonomy} &middot; {occupation.external_code}
      </p>
    </article>
  );
}

function SourceSection({ source }: { source: MarketSourceOut }) {
  return (
    <section className="market-source">
      <header className="market-source-header">
        <h4>
          <a href={source.source_url} target="_blank" rel="noopener noreferrer">
            {source.source_name}
          </a>
        </h4>
        <span className="market-source-period">
          {source.reference_period_label}
          {source.published_date ? ` · published ${source.published_date}` : ''}
        </span>
      </header>

      {/* Prominent, above this source's numbers - never a footnote. The
          case this exists for is the survey's India sample, which reads
          high against the broad Indian market. */}
      {source.representativeness_note && (
        <div className="market-warning market-warning-representativeness" role="note">
          <strong>How representative is this?</strong> {source.representativeness_note}
        </div>
      )}

      {source.excludes_variable_compensation && (
        <div className="market-warning" role="note">
          <strong>These figures exclude bonuses and equity.</strong> They cover base pay,
          commissions and production bonuses only. If your offer includes bonus or equity, compare
          those separately, and compare against your <strong>gross</strong> pay before tax, never
          your net.
        </div>
      )}

      {source.occupations.map((occupation) => (
        <OccupationCard key={occupation.external_code} occupation={occupation} />
      ))}

      <p className="market-methodology">
        <strong>What this counts as pay:</strong> {source.wage_definition_note}
      </p>
      <p className="market-methodology">{source.methodology_note}</p>
    </section>
  );
}

/**
 * Market context is a STATISTICAL ESTIMATE from a survey or a
 * statistical agency, not a computed figure. That distinction is carried
 * by construction: this panel has its own container and accent, renders
 * distributions rather than single values, and never appears inside the
 * calculation's own results markup.
 *
 * Since Phase 11 there can be more than one source for the same role and
 * country, and they disagree - BLS measures employer-reported base pay,
 * the survey measures self-reported total compensation. Both are shown,
 * each under its own heading with its own methodology, and they are
 * NEVER averaged or reconciled: combining two differently-methodologied
 * figures would produce a number neither source reported.
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

  // Defensive `?? []`: this panel sits inside the results view, so a
  // malformed payload must degrade to "nothing to show" rather than
  // throwing and taking the user's actual calculation down with it.
  const sources = state.kind === 'loaded' ? (state.context.sources ?? []) : [];

  return (
    <section className="market-context-panel">
      <h3>Market context</h3>
      <p className="market-context-intro">
        Published wage statistics for comparable occupations. These are survey{' '}
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
        // indistinguishable from a loading failure.
        <p className="market-unavailable" role="status">
          {state.context.unavailable_reason}
        </p>
      )}

      {state.kind === 'loaded' && state.context.available && sources.length > 0 && (
        <>
          {sources.length > 1 && (
            <p className="market-multi-source" role="note">
              <strong>{sources.length} sources are shown below, separately.</strong> They measure
              different things and will not agree &mdash; they are never combined or averaged,
              because an average of two different methodologies would be a number neither source
              reported. Read each on its own terms.
            </p>
          )}

          {sources.map((source) => (
            <SourceSection key={source.source_key} source={source} />
          ))}

          <p className="market-context-disclaimer">
            Experience bands are years of professional experience as reported to the source. They
            are not job levels &mdash; no source publishes a mapping from years to titles like
            &ldquo;senior&rdquo;, so none is implied here.
          </p>
        </>
      )}
    </section>
  );
}
