import type { CalculationOut } from '../../api/client';
import { parseBreakdown } from './breakdown';
import { formatCurrency, formatRate } from './format';
import { componentTypeLabel, taxComponentLabel } from './labels';

export interface ResultsViewProps {
  calculation: CalculationOut;
  onReset: () => void;
}

export function ResultsView({ calculation, onReset }: ResultsViewProps) {
  const breakdown = parseBreakdown(calculation.breakdown);
  // Falls back to the calculation's own target currency the breakdown is
  // meant to reflect, if the free-form breakdown didn't parse - all the
  // strongly-typed summary fields below still render either way.
  const currency = breakdown?.target_currency ?? '';

  return (
    <section>
      <h2>Result</h2>

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
          {breakdown.tax.standard_deduction !== null && (
            <p>
              Standard deduction applied to income tax:{' '}
              {formatCurrency(breakdown.tax.standard_deduction, currency)}
            </p>
          )}
          {breakdown.tax.components.map((taxComponent) => (
            <div key={taxComponent.component}>
              <h4>
                {taxComponentLabel(taxComponent.component)} —{' '}
                {formatCurrency(taxComponent.total_tax, currency)}
              </h4>
              <p>Taxable base: {formatCurrency(taxComponent.taxable_base, currency)}</p>
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
                        {formatCurrency(bracket.lower_bound, currency)} –{' '}
                        {bracket.upper_bound === null
                          ? '∞'
                          : formatCurrency(bracket.upper_bound, currency)}
                      </td>
                      <td>{formatRate(bracket.rate)}</td>
                      <td>{formatCurrency(bracket.taxable_amount, currency)}</td>
                      <td>{formatCurrency(bracket.tax_amount, currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
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

      <button type="button" onClick={onReset}>
        New calculation
      </button>
    </section>
  );
}
