import { useState } from 'react';

import { AuthProvider, useAuth } from './features/auth/AuthContext';
import { AuthForms } from './features/auth/AuthForms';
import { Calculator } from './features/calculator/Calculator';
import { ComparisonsView } from './features/comparison/ComparisonsView';
import { HealthStatus } from './features/health/HealthStatus';
import { HistoryView } from './features/history/HistoryView';

type View = 'calculator' | 'history' | 'compare' | 'auth';

function AppContent() {
  const { status, email, logout } = useAuth();
  const [view, setView] = useState<View>('calculator');

  function handleLogout() {
    void logout();
    setView('calculator');
  }

  // history/compare/auth only make sense in certain auth states - fall
  // back to the calculator rather than rendering an impossible
  // combination (history or comparisons while logged out - comparisons
  // inherently operate on saved history, which anonymous use doesn't
  // have, same boundary Phase 5 already established for history itself -
  // or the login form while already logged in, e.g. right after a
  // successful login/register).
  const effectiveView: View =
    ((view === 'history' || view === 'compare') && status !== 'authenticated') ||
    (view === 'auth' && status === 'authenticated')
      ? 'calculator'
      : view;

  return (
    <main>
      <div className="app-header">
        <h1>AI Global Compensation Intelligence</h1>
        <div className="auth-status">
          {status === 'authenticated' && (
            <>
              <span>Logged in as {email}</span>
              <button type="button" className="link-button" onClick={() => setView('history')}>
                My calculations
              </button>
              <button type="button" className="link-button" onClick={() => setView('compare')}>
                Compare
              </button>
              <button type="button" className="link-button" onClick={handleLogout}>
                Log out
              </button>
            </>
          )}
          {status === 'anonymous' && (
            <button type="button" className="link-button" onClick={() => setView('auth')}>
              Log in
            </button>
          )}
        </div>
      </div>

      <HealthStatus />

      {/* The calculator is the default view and stays reachable
          regardless of auth status - including while "loading" (the
          silent refresh-token check on mount) - so a logged-out user's
          Phase 4 flow is never gated behind auth resolving first. */}
      {effectiveView === 'auth' && <AuthForms onSuccess={() => setView('calculator')} />}
      {effectiveView === 'history' && <HistoryView />}
      {effectiveView === 'compare' && <ComparisonsView />}
      {effectiveView === 'calculator' && <Calculator />}
    </main>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
