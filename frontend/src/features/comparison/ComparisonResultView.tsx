import type { ComparisonDetailOut } from '../../api/client';
import { AIInsightPanel } from '../ai/AIInsightPanel';
import { ResultsView } from '../calculator/ResultsView';
import { formatCurrency } from '../calculator/format';
import { gapMetricLabel, GAP_METRIC_ORDER } from './labels';

export interface ComparisonResultViewProps {
  comparison: ComparisonDetailOut;
  onBack: () => void;
}

function noop() {
  // Per-offer breakdowns below are read-only (showActions=false hides
  // the "New calculation" button that would call this) - it exists only
  // to satisfy ResultsView's required prop.
}

export function ComparisonResultView({ comparison, onBack }: ComparisonResultViewProps) {
  const currency = comparison.comparison_currency;
  // Position within `entries`/`calculations` is stable (both mirror the
  // order calculation_ids were submitted in, per the backend's own
  // ordering guarantee) - used only to label offers "Offer 1", "Offer 2"
  // since individual calculations don't carry a country/job label of
  // their own yet.
  const offerNumberById = new Map(
    comparison.entries.map((e, index) => [e.calculation_id, index + 1]),
  );

  return (
    <section>
      <h2>{comparison.name}</h2>
      <p>
        Compared in {currency}, as of {comparison.as_of_date}.
      </p>

      <h3>Side-by-side</h3>
      <table>
        <thead>
          <tr>
            <th scope="col">Offer</th>
            <th scope="col">Original currency</th>
            <th scope="col">Rate used</th>
            <th scope="col">Gross</th>
            <th scope="col">Total compensation</th>
            <th scope="col">Total tax</th>
            <th scope="col">Net</th>
          </tr>
        </thead>
        <tbody>
          {comparison.entries.map((entry) => (
            <tr key={entry.calculation_id}>
              <td>Offer {offerNumberById.get(entry.calculation_id)}</td>
              <td>{entry.source_currency}</td>
              <td>
                {entry.rate_used !== null
                  ? `1 ${entry.source_currency} = ${entry.rate_used} ${currency}`
                  : 'same currency'}
              </td>
              <td>{formatCurrency(entry.gross_amount, currency)}</td>
              <td>{formatCurrency(entry.total_compensation_amount, currency)}</td>
              <td>
                {entry.total_tax_amount !== null
                  ? formatCurrency(entry.total_tax_amount, currency)
                  : 'no tax data'}
              </td>
              <td>
                {entry.net_amount !== null
                  ? formatCurrency(entry.net_amount, currency)
                  : 'no tax data'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Gap analysis</h3>
      {GAP_METRIC_ORDER.map((metric) => {
        const gap = comparison.gap_analysis[metric];
        if (!gap) {
          return (
            <p key={metric}>
              {gapMetricLabel(metric)}: not available for every offer (at least one has no figure
              for it).
            </p>
          );
        }
        const leaderOfferNumber = offerNumberById.get(gap.leader_calculation_id);
        return (
          <div key={metric}>
            <h4>
              {gapMetricLabel(metric)} — Offer {leaderOfferNumber} is ahead
            </h4>
            <table>
              <thead>
                <tr>
                  <th scope="col">Offer</th>
                  <th scope="col">Gap (absolute)</th>
                  <th scope="col">Gap (percent)</th>
                </tr>
              </thead>
              <tbody>
                {gap.entries.map((g) => {
                  const isLeader = g.calculation_id === gap.leader_calculation_id;
                  return (
                    <tr key={g.calculation_id}>
                      <td>
                        Offer {offerNumberById.get(g.calculation_id)}
                        {isLeader ? ' (leader)' : ''}
                      </td>
                      <td>{formatCurrency(g.gap_absolute, currency)}</td>
                      {/* gap_percent is already a percentage value (e.g.
                          "43.71" meaning 43.71%), not a fraction -
                          formatRate (used for tax bracket rates
                          elsewhere) expects the opposite and would be
                          the wrong tool here. */}
                      <td>{g.gap_percent !== null ? `${g.gap_percent}%` : 'n/a'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}

      {/* Comparisons always require auth + ownership to create (Phase
          7), and this view only ever renders a comparison the current
          user already owns - no extra gating needed here, unlike the
          per-offer ResultsView below (which suppresses its own AI
          insight panel, since this one already covers all the offers
          together, the more useful framing for a comparison). */}
      <AIInsightPanel target={{ comparisonId: comparison.id }} />

      <h3>Per-offer detail</h3>
      {comparison.calculations.map((calculation, index) => (
        <ResultsView
          key={calculation.id}
          calculation={calculation}
          onReset={noop}
          showActions={false}
          heading={`Offer ${index + 1}`}
        />
      ))}

      <button type="button" onClick={onBack}>
        Back to comparisons
      </button>
    </section>
  );
}
