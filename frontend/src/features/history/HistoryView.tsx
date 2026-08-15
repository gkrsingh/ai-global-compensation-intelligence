import { useEffect, useState } from 'react';

import { fetchMyCalculations, type CalculationOut } from '../../api/client';
import { parseBreakdown } from '../calculator/breakdown';
import { formatCurrency } from '../calculator/format';
import { ResultsView } from '../calculator/ResultsView';

const PAGE_SIZE = 10;

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'loaded'; items: CalculationOut[]; total: number; offset: number };

export function HistoryView() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' });
  const [selected, setSelected] = useState<CalculationOut | null>(null);

  function load(offset: number) {
    setState({ kind: 'loading' });
    fetchMyCalculations(PAGE_SIZE, offset)
      .then((page) => {
        setState({ kind: 'loaded', items: page.items, total: page.total, offset: page.offset });
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : 'Unknown error';
        setState({ kind: 'error', message });
      });
  }

  useEffect(() => {
    load(0);
    // Deliberately runs once on mount only - HistoryView is remounted
    // fresh each time the user navigates to it (see App.tsx's
    // state-based view switching), so there's no stale-closure risk from
    // an empty dependency array here.
  }, []);

  if (selected) {
    return <ResultsView calculation={selected} onReset={() => setSelected(null)} />;
  }

  if (state.kind === 'loading') {
    return <p>Loading your calculations…</p>;
  }

  if (state.kind === 'error') {
    return <p role="alert">Could not load your calculations: {state.message}</p>;
  }

  if (state.items.length === 0) {
    return <p>You haven&apos;t saved any calculations yet.</p>;
  }

  return (
    <section>
      <h2>My calculations</h2>
      {state.items.map((calculation) => {
        const breakdown = parseBreakdown(calculation.breakdown);
        const currency = breakdown?.target_currency ?? '';
        return (
          <button
            key={calculation.id}
            type="button"
            className="calculation-summary-row"
            onClick={() => setSelected(calculation)}
          >
            <span>{new Date(calculation.created_at).toLocaleString()}</span>
            <span>Gross: {formatCurrency(calculation.gross_amount, currency)}</span>
            <span>
              {calculation.net_amount !== null
                ? `Net: ${formatCurrency(calculation.net_amount, currency)}`
                : 'No tax data'}
            </span>
          </button>
        );
      })}

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
    </section>
  );
}
