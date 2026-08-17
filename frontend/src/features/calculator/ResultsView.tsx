import type { CalculationOut } from '../../api/client';
import { AIInsightPanel } from '../ai/AIInsightPanel';
import { MarketContextPanel } from '../market/MarketContextPanel';
import { parseBreakdown } from './breakdown';
import { formatCurrency, formatRate } from './format';
import { componentTypeLabel, taxComponentLabel } from './labels';

export interface ResultsViewProps {
  calculation: CalculationOut;
  onReset: () => void;
  // Both default to the original standalone-calculator behavior -
  // callers embedding this view read-only inside something else (e.g.
  // one offer within a Comparison) override them rather than every
  // existing caller needing to opt in.
  heading?: string;
  showActions?: boolean;
}

export function ResultsView({
  calculation,
  onReset,
  heading = 'Result',
  showActions = true,
}: ResultsViewProps) {
  const breakdown = parseBreakdown(calculation.breakdown);
  // Falls back to the calculation's own target currency the breakdown is
  // meant to reflect, if the free-form breakdown didn't parse - all the
  // strongly-typed summary fields below still render either way.
  const currency = breakdown?.target_currency ?? '';

  return (
    <section>
      <h2>{heading}</h2>

      {showActions && calculation.user_id !== null && <p role="status">Saved to your history.</p>}

      <dl className="results-summary">
        <div>
          <dt>Gross compensation (cash only, before tax)</dt>
          <dd>{formatCurrency(calculation.gross_amount, currency)}</dd>
        </div>
        <div>
          <dt>Total compensation (all components, including equity &amp; benefits)</dt>
          <dd>{formatCurrency(calculation.total_compensation_amount, currency)}</dd>
        </div>
        {calculation.total_tax_amount !== null && (
          <div>
            <dt>Total tax</dt>
            <dd>{formatCurrency(calculation.total_tax_amount, currency)}</dd>
          </div>
        )}
        {calculation.net_amount !== null && (
          <div>
            <dt>Net compensation (cash only, after tax)</dt>
            <dd>{formatCurrency(calculation.net_amount, currency)}</dd>
          </div>
        )}
      </dl>

      {calculation.total_tax_amount === null && (
        <p role="status">
          No applicable tax rule set was found for this country and date, so tax and net
          compensation could not be calculated. The figures above (gross and total compensation)
          don&apos;t depend on tax and are still accurate.
        </p>
      )}

      {breakdown && breakdown.components.length > 0 && (
        <>
          <h3>Compensation components</h3>
          <table>
            <thead>
              <tr>
                <th scope="col">Type</th>
                <th scope="col">Original</th>
                <th scope="col">Converted</th>
                <th scope="col">Counts toward gross</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.components.map((component, index) => (
                <tr key={index}>
                  <td>
                    {componentTypeLabel(component.type)}
                    {component.description ? ` (${component.description})` : ''}
                  </td>
                  <td>{formatCurrency(component.original_amount, component.original_currency)}</td>
                  <td>{formatCurrency(component.converted_amount, currency)}</td>
                  <td>{component.counts_toward_gross ? 'Yes' : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {breakdown?.tax && breakdown.tax.components.length > 0 && (
        <>
          <h3>Tax breakdown</h3>
          {/* The tax law's own currency (e.g. India's brackets are INR),
              which can differ from `currency` (target_currency) above when
              the caller asks to see totals in a different currency than
              the tax law is denominated in - the figures below must use
              this one, not the outer target currency. */}
          {(() => {
            const taxCurrency = breakdown.tax.currency;
            return (
              <>
                {taxCurrency !== currency && (
                  <p>
                    Tax figures below are shown in {taxCurrency}, the currency this tax law is
                    denominated in, not {currency}.
                  </p>
                )}
                {breakdown.tax.standard_deduction !== null && (
                  <p>
                    Standard deduction applied to income tax:{' '}
                    {formatCurrency(breakdown.tax.standard_deduction, taxCurrency)}
                  </p>
                )}
                {breakdown.tax.components.map((taxComponent) => (
                  <div key={taxComponent.component}>
                    <h4>
                      {taxComponentLabel(taxComponent.component)} —{' '}
                      {formatCurrency(taxComponent.total_tax, taxCurrency)}
                    </h4>
                    <p>Taxable base: {formatCurrency(taxComponent.taxable_base, taxCurrency)}</p>
                    <table>
                      <thead>
                        <tr>
                          <th scope="col">Bracket</th>
                          <th scope="col">Rate</th>
                          <th scope="col">Taxable amount</th>
                          <th scope="col">Tax</th>
                        </tr>
                      </thead>
                      <tbody>
                        {taxComponent.brackets.map((bracket, index) => (
                          <tr key={index}>
                            <td>
                              {formatCurrency(bracket.lower_bound, taxCurrency)} –{' '}
                              {bracket.upper_bound === null
                                ? '∞'
                                : formatCurrency(bracket.upper_bound, taxCurrency)}
                            </td>
                            <td>{formatRate(bracket.rate)}</td>
                            <td>{formatCurrency(bracket.taxable_amount, taxCurrency)}</td>
                            <td>{formatCurrency(bracket.tax_amount, taxCurrency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
              </>
            );
          })()}
        </>
      )}

      {breakdown && Object.keys(breakdown.rates_used).length > 0 && (
        <p>
          Exchange rates used:{' '}
          {Object.entries(breakdown.rates_used)
            .map(([pair, rate]) => `${pair} = ${rate}`)
            .join(', ')}
        </p>
      )}

      {/* AI insight requires auth + ownership on the backend, and the
          only way a calculation with a non-null user_id ever reaches
          this component is if it's already scoped to the current
          viewer (HistoryView only ever loads from /calculations/mine;
          the calculator's own fresh result is only ever tagged to
          whoever is currently logged in) - no separate frontend-side
          user-id comparison needed. Suppressed for embedded, read-only
          per-offer views inside a Comparison (showActions=false) -
          that comparison already gets its own, more relevant insight
          covering all offers at once. */}
      {/* Market context needs a job family to map onto a published
          occupation, and the calculator does not require one - so this
          is simply absent when the user did not pick a family, rather
          than rendering an empty or guessed panel. Unlike the AI panel
          it needs no auth (public government statistics) and is shown
          for embedded per-offer views too, since each offer's own
          country/role is exactly what its market comparison depends
          on. */}
      {/* `!= null` rather than `!== null`: this also covers an absent
          field, not just an explicit null. A stale client or an older
          cached payload without job_family_id would otherwise slip
          through as "present" and request market context for
          undefined. */}
      {calculation.job_family_id != null && calculation.country_code && (
        <MarketContextPanel
          jobFamilyId={calculation.job_family_id}
          countryCode={calculation.country_code}
        />
      )}

      {showActions && calculation.user_id !== null && (
        <AIInsightPanel target={{ calculationId: calculation.id }} />
      )}

      {showActions && (
        <button type="button" onClick={onReset}>
          New calculation
        </button>
      )}
    </section>
  );
}
