import { useEffect, useState } from 'react';

import { fetchComparison, fetchMyComparisons, type ComparisonDetailOut } from '../../api/client';
import { ComparisonBuilder } from './ComparisonBuilder';
import { ComparisonResultView } from './ComparisonResultView';

const PAGE_SIZE = 10;

type ComparisonSummary = Awaited<ReturnType<typeof fetchMyComparisons>>['items'][number];

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'loaded'; items: ComparisonSummary[]; total: number; offset: number };

type ViewState =
  | { kind: 'list' }
  | { kind: 'build' }
  | { kind: 'detail'; comparison: ComparisonDetailOut }
  | { kind: 'detail-loading' }
  | { kind: 'detail-error'; message: string };

export function ComparisonsView() {
  const [view, setView] = useState<ViewState>({ kind: 'list' });
  const [listState, setListState] = useState<ListState>({ kind: 'loading' });

  function loadList(offset: number) {
    setListState({ kind: 'loading' });
    fetchMyComparisons(PAGE_SIZE, offset)
      .then((page) => {
        setListState({ kind: 'loaded', items: page.items, total: page.total, offset: page.offset });
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : 'Unknown error';
        setListState({ kind: 'error', message });
      });
  }

  useEffect(() => {
    if (view.kind === 'list') {
      loadList(0);
    }
    // Re-fetches every time we land back on the list - in particular
    // right after creating a new comparison, so it shows up without a
    // manual refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.kind]);

  function openComparison(id: number) {
    setView({ kind: 'detail-loading' });
    fetchComparison(id)
      .then((comparison) => setView({ kind: 'detail', comparison }))
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : 'Unknown error';
        setView({ kind: 'detail-error', message });
      });
  }

  if (view.kind === 'build') {
    return (
      <ComparisonBuilder
        onCreated={(comparison) => setView({ kind: 'detail', comparison })}
        onCancel={() => setView({ kind: 'list' })}
      />
    );
  }

  if (view.kind === 'detail') {
    return (
      <ComparisonResultView comparison={view.comparison} onBack={() => setView({ kind: 'list' })} />
    );
  }

  if (view.kind === 'detail-loading') {
    return <p>Loading comparison…</p>;
  }

  if (view.kind === 'detail-error') {
    return (
      <>
        <p role="alert">Could not load that comparison: {view.message}</p>
        <button type="button" onClick={() => setView({ kind: 'list' })}>
          Back to comparisons
        </button>
      </>
    );
  }

  return (
    <section>
      <h2>My comparisons</h2>
      <div className="component-row">
        <button type="button" onClick={() => setView({ kind: 'build' })}>
          New comparison
        </button>
      </div>

      {listState.kind === 'loading' && <p>Loading your comparisons…</p>}
      {listState.kind === 'error' && (
        <p role="alert">Could not load your comparisons: {listState.message}</p>
      )}
      {listState.kind === 'loaded' && listState.items.length === 0 && (
        <p>You haven&apos;t created any comparisons yet.</p>
      )}

      {listState.kind === 'loaded' &&
        listState.items.map((comparison) => (
          <button
            key={comparison.id}
            type="button"
            className="calculation-summary-row"
            onClick={() => openComparison(comparison.id)}
          >
            <span>{comparison.name}</span>
            <span>{comparison.calculation_count} offers</span>
            <span>{comparison.comparison_currency}</span>
            <span>{new Date(comparison.created_at).toLocaleString()}</span>
          </button>
        ))}

      {listState.kind === 'loaded' && (
        <div className="component-row">
          <button
            type="button"
            disabled={listState.offset === 0}
            onClick={() => loadList(Math.max(0, listState.offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <button
            type="button"
            disabled={listState.offset + listState.items.length >= listState.total}
            onClick={() => loadList(listState.offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      )}
    </section>
  );
}
