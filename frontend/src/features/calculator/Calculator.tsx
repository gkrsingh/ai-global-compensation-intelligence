import { useState } from 'react';

import {
  ApiError,
  createCalculation,
  type CalculationOut,
  type CompensationInputCreate,
} from '../../api/client';
import { friendlyErrorLines } from '../../api/errors';
import { useAuth } from '../auth/AuthContext';
import { CompensationForm } from './CompensationForm';
import { ResultsView } from './ResultsView';

type CalculatorState =
  | { kind: 'form'; submitting: boolean; error: ApiError | null }
  | { kind: 'result'; calculation: CalculationOut; sessionExpired: boolean };

export function Calculator() {
  const { handleAuthWarning } = useAuth();
  const [state, setState] = useState<CalculatorState>({
    kind: 'form',
    submitting: false,
    error: null,
  });

  function handleSubmit(payload: CompensationInputCreate) {
    setState({ kind: 'form', submitting: true, error: null });
    createCalculation(payload)
      .then(({ calculation, authWarning }) => {
        if (authWarning) {
          // The calculation still succeeded (see createCalculation's
          // docstring / the backend's AUTH_WARNING_HEADER) - the stale
          // token itself is now dead, so drop back to a clean anonymous
          // state rather than pretending the session is still good.
          handleAuthWarning();
        }
        setState({ kind: 'result', calculation, sessionExpired: authWarning !== null });
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
    return (
      <>
        {state.sessionExpired && (
          <div role="status" className="notice-banner">
            Your session expired, so this calculation was saved anonymously, not to your history.
            Log in again to keep saving future calculations.
          </div>
        )}
        <ResultsView calculation={state.calculation} onReset={handleReset} />
      </>
    );
  }

  return (
    <>
      {state.error && (
        <div role="alert" className="error-banner">
          <ul>
            {friendlyErrorLines(state.error).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      <CompensationForm onSubmit={handleSubmit} submitting={state.submitting} />
    </>
  );
}
