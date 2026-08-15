import { useState } from 'react';

import type { CompensationInputCreate } from './api/client';
import { CompensationForm } from './features/calculator/CompensationForm';
import { HealthStatus } from './features/health/HealthStatus';

// TEMPORARY step-3 checkpoint stub: replaced in step 4 by real submission
// handling (createCalculation) and a ResultsView. Wired in now so
// CompensationForm can be verified against the real backend in a real
// browser, not just imagined to work.
function App() {
  const [lastSubmitted, setLastSubmitted] = useState<CompensationInputCreate | null>(null);

  return (
    <main>
      <h1>AI Global Compensation Intelligence</h1>
      <HealthStatus />
      <CompensationForm onSubmit={setLastSubmitted} />
      {lastSubmitted && <pre>{JSON.stringify(lastSubmitted, null, 2)}</pre>}
    </main>
  );
}

export default App;
