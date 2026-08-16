import { useEffect, useState, type FormEvent } from 'react';

import {
  ApiError,
  createComparison,
  fetchCountries,
  fetchMyCalculations,
  type CalculationOut,
  type ComparisonDetailOut,
  type Currency,
} from '../../api/client';
import { friendlyErrorLines } from '../../api/errors';
import { parseBreakdown } from '../calculator/breakdown';
import { formatCurrency } from '../calculator/format';

const PAGE_SIZE = 10;

type CalculationsLoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'loaded'; items: CalculationOut[]; total: number; offset: number };

export interface ComparisonBuilderProps {
  onCreated: (comparison: ComparisonDetailOut) => void;
  onCancel: () => void;
}

export function ComparisonBuilder({ onCreated, onCancel }: ComparisonBuilderProps) {
  const [state, setState] = useState<CalculationsLoadState>({ kind: 'loading' });
  // A Set survives across pages, so a selection made on page 1 is not
  // lost when the user pages forward to find a second offer - the
  // backend receives the full accumulated set on submit, not just
  // whatever page happens to be showing.
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [name, setName] = useState('');
  const [currencyCode, setCurrencyCode] = useState('');
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  function load(offset: number) {
    setState({ kind: 'loading' });
    fetchMyCalculations(PAGE_SIZE, offset)
      .then((page) => {
        setState({ kind: 'loaded', items: page.items, total: page.total, offset: page.offset });
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : 'Unknown error';
        setState({ kind: 'error', message });
      });
  }

  useEffect(() => {
    load(0);
    // Runs once on mount, same reasoning as HistoryView's own effect:
    // this component is remounted fresh each time the user navigates
    // here (App.tsx's state-based view switching).
  }, []);

  useEffect(() => {
    fetchCountries()
      .then((countries) => {
        const byCode = new Map<string, Currency>();
        for (const country of countries) {
          byCode.set(country.default_currency.code, country.default_currency);
        }
        const list = [...byCode.values()].sort((a, b) => a.code.localeCompare(b.code));
        setCurrencies(list);
        if (list.length > 0) {
          setCurrencyCode(list[0].code);
        }
      })
      .catch(() => {
        // Non-fatal, mirrors CompensationForm's regime-lookup precedent:
        // the currency dropdown just stays empty rather than the whole
        // builder breaking over it - submit is disabled until one loads.
      });
  }, []);

  function toggle(id: number) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (selectedIds.size < 2 || !currencyCode || name.trim() === '') {
      return;
    }
    setSubmitting(true);
    setError(null);
    createComparison({
      name: name.trim(),
      comparison_currency_code: currencyCode,
      calculation_ids: [...selectedIds],
    })
      .then((comparison) => {
        onCreated(comparison);
      })
      .catch((err: unknown) => {
        const apiError =
          err instanceof ApiError
            ? err
            : new ApiError('unknown_error', 'An unexpected error occurred', null);
        setError(apiError);
        setSubmitting(false);
      });
  }

  return (
    <section>
      <h2>New comparison</h2>

      {error && (
        <div role="alert" className="error-banner">
          <ul>
            {friendlyErrorLines(error).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="comparison-name">Comparison name</label>
          <input
            id="comparison-name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. India vs Spain offer"
            required
          />
        </div>

        <div className="field">
          <label htmlFor="comparison-currency">Compare in currency</label>
          <select
            id="comparison-currency"
            value={currencyCode}
            onChange={(event) => setCurrencyCode(event.target.value)}
            required
          >
            {currencies.length === 0 && <option value="">Loading…</option>}
            {currencies.map((currency) => (
              <option key={currency.code} value={currency.code}>
                {currency.code} - {currency.name}
              </option>
            ))}
          </select>
        </div>

        <p>Select 2 or more calculations to compare ({selectedIds.size} selected):</p>

        {state.kind === 'loading' && <p>Loading your calculations…</p>}
        {state.kind === 'error' && (
          <p role="alert">Could not load your calculations: {state.message}</p>
        )}
        {state.kind === 'loaded' && state.items.length === 0 && (
          <p>You haven&apos;t saved any calculations yet - nothing to compare.</p>
        )}

        {state.kind === 'loaded' &&
          state.items.map((calculation) => {
            const breakdown = parseBreakdown(calculation.breakdown);
            const currency = breakdown?.target_currency ?? '';
            const checkboxId = `comparison-select-${calculation.id}`;
            return (
              <div key={calculation.id} className="calculation-summary-row">
                <input
                  id={checkboxId}
                  type="checkbox"
                  checked={selectedIds.has(calculation.id)}
                  onChange={() => toggle(calculation.id)}
                />
                <label htmlFor={checkboxId}>
                  <span>{new Date(calculation.created_at).toLocaleString()}</span>{' '}
                  <span>Gross: {formatCurrency(calculation.gross_amount, currency)}</span>{' '}
                  <span>
                    {calculation.net_amount !== null
                      ? `Net: ${formatCurrency(calculation.net_amount, currency)}`
                      : 'No tax data'}
                  </span>
                </label>
              </div>
            );
          })}

        {state.kind === 'loaded' && (
          <div className="component-row">
            <button
              type="button"
              disabled={state.offset === 0}
              onClick={() => load(Math.max(0, state.offset - PAGE_SIZE))}
            >
              Previous
            </button>
            <button
              type="button"
              disabled={state.offset + state.items.length >= state.total}
              onClick={() => load(state.offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        )}

        <div className="component-row">
          <button type="submit" disabled={submitting || selectedIds.size < 2 || !currencyCode}>
            {submitting ? 'Creating…' : 'Create comparison'}
          </button>
          <button type="button" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}
