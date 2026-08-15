import { useState } from 'react';

import {
  ApiError,
  createCalculation,
  type CalculationOut,
  type CompensationInputCreate,
} from '../../api/client';
import { CompensationForm } from './CompensationForm';
import { ResultsView } from './ResultsView';

type CalculatorState =
  | { kind: 'form'; submitting: boolean; error: ApiError | null }
  | { kind: 'result'; calculation: CalculationOut };

export function Calculator() {
  const [state, setState] = useState<CalculatorState>({
    kind: 'form',
    submitting: false,
    error: null,
  });

  function handleSubmit(payload: CompensationInputCreate) {
    setState({ kind: 'form', submitting: true, error: null });
    createCalculation(payload)
      .then((calculation) => {
        setState({ kind: 'result', calculation });
      })
      .catch((error: unknown) => {
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError('unknown_error', 'An unexpected error occurred', null);
        setState({ kind: 'form', submitting: false, error: apiError });
      });
  }

  function handleReset() {
    setState({ kind: 'form', submitting: false, error: null });
  }

  if (state.kind === 'result') {
    return <ResultsView calculation={state.calculation} onReset={handleReset} />;
  }

  return (
    <>
      {state.error && (
        <div role="alert" className="error-banner">
          {state.error.message}
        </div>
      )}
      <CompensationForm onSubmit={handleSubmit} submitting={state.submitting} />
    </>
  );
}
