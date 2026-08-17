import type { components } from './schema';
import { getAccessToken } from './tokenStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export interface HealthCheckResponse {
  status: string;
  checks: Record<string, string>;
}

export async function fetchHealth(): Promise<HealthCheckResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);
  return (await response.json()) as HealthCheckResponse;
}

export type Country = components['schemas']['CountryOut'];
export type Currency = components['schemas']['CurrencyOut'];
export type ComponentType = components['schemas']['ComponentType'];
export type CompensationComponentIn = components['schemas']['CompensationComponentIn'];
export type CompensationInputCreate = components['schemas']['CompensationInputCreate'];
export type CalculationOut = components['schemas']['CalculationOut'];
export type TaxRuleSet = components['schemas']['TaxRuleSetOut'];
export type UserOut = components['schemas']['UserOut'];
export type TokenPairOut = components['schemas']['TokenPairOut'];
export type AccessTokenOut = components['schemas']['AccessTokenOut'];
export type PaginatedCalculationsOut = components['schemas']['PaginatedCalculationsOut'];
export type ComparisonCreate = components['schemas']['ComparisonCreate'];
export type ComparisonDetailOut = components['schemas']['ComparisonDetailOut'];
export type ComparisonEntryOut = components['schemas']['ComparisonEntryOut'];
export type ComparisonSummaryOut = components['schemas']['ComparisonSummaryOut'];
export type MetricGapAnalysisOut = components['schemas']['MetricGapAnalysisOut'];
export type MetricGapEntryOut = components['schemas']['MetricGapEntryOut'];
export type PaginatedComparisonsOut = components['schemas']['PaginatedComparisonsOut'];
export type AIInsightOut = components['schemas']['AIInsightOut'];
export type MarketContextOut = components['schemas']['MarketContextOut'];
export type MarketOccupationOut = components['schemas']['MarketOccupationOut'];
export type WageDistributionOut = components['schemas']['WageDistributionOut'];
export type MatchQuality = components['schemas']['MatchQuality'];
export type JobFamily = components['schemas']['JobFamilyOut'];

/**
 * The FastAPI-generated OpenAPI schema documents 422 responses as
 * HTTPValidationError (FastAPI's built-in shape), but every error response
 * from this API - validation failures included - actually goes through our
 * own exception handlers (app/core/exceptions.py) and comes back as this
 * envelope instead. Confirmed against the real running backend, not just
 * assumed from the generated types.
 */
export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export class ApiError extends Error {
  code: string;
  details: unknown;

  constructor(code: string, message: string, details: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.details = details;
  }
}

async function parseErrorResponse(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorEnvelope;
    return new ApiError(body.error.code, body.error.message, body.error.details);
  } catch {
    return new ApiError('unknown_error', `Request failed with status ${response.status}`, null);
  }
}

export async function fetchCountries(): Promise<Country[]> {
  const response = await fetch(`${API_BASE_URL}/countries`);
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as Country[];
}

export async function fetchJobFamilies(): Promise<JobFamily[]> {
  const response = await fetch(`${API_BASE_URL}/job-families`);
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as JobFamily[];
}

export async function fetchTaxRuleSets(countryCode: string): Promise<TaxRuleSet[]> {
  const response = await fetch(`${API_BASE_URL}/countries/${countryCode}/tax-rule-sets`);
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as TaxRuleSet[];
}

// Matches the backend's AUTH_WARNING_HEADER (app/compensation/api.py) -
// present when a bearer token was sent but rejected, so the calculation
// still succeeded anonymously rather than failing outright.
const AUTH_WARNING_HEADER = 'X-Auth-Warning';

export interface CreateCalculationResult {
  calculation: CalculationOut;
  authWarning: string | null;
}

export async function createCalculation(
  payload: CompensationInputCreate,
): Promise<CreateCalculationResult> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const accessToken = getAccessToken();
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${API_BASE_URL}/calculations`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return {
    calculation: (await response.json()) as CalculationOut,
    authWarning: response.headers.get(AUTH_WARNING_HEADER),
  };
}

export async function register(email: string, password: string): Promise<UserOut> {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as UserOut;
}

export async function login(email: string, password: string): Promise<TokenPairOut> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as TokenPairOut;
}

export async function refreshAccessToken(refreshToken: string): Promise<AccessTokenOut> {
  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as AccessTokenOut;
}

export async function logoutRequest(refreshToken: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/auth/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
}

export async function fetchMyCalculations(
  limit: number,
  offset: number,
): Promise<PaginatedCalculationsOut> {
  const accessToken = getAccessToken();
  const headers: Record<string, string> = accessToken
    ? { Authorization: `Bearer ${accessToken}` }
    : {};
  const response = await fetch(
    `${API_BASE_URL}/calculations/mine?limit=${limit}&offset=${offset}`,
    { headers },
  );
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as PaginatedCalculationsOut;
}

// All three comparison endpoints require auth - unlike POST
// /calculations, there's no anonymous equivalent (a comparison
// inherently operates on saved history). Callers are expected to only
// reach these views while authenticated, so an absent access token is
// sent as-is rather than special-cased - the backend's own 401
// "not_authenticated" surfaces the same way any other auth failure would.
function _authHeaders(): Record<string, string> {
  const accessToken = getAccessToken();
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

export async function createComparison(payload: ComparisonCreate): Promise<ComparisonDetailOut> {
  const response = await fetch(`${API_BASE_URL}/comparisons`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ..._authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as ComparisonDetailOut;
}

export async function fetchMyComparisons(
  limit: number,
  offset: number,
): Promise<PaginatedComparisonsOut> {
  const response = await fetch(`${API_BASE_URL}/comparisons/mine?limit=${limit}&offset=${offset}`, {
    headers: _authHeaders(),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as PaginatedComparisonsOut;
}

export async function fetchComparison(id: number): Promise<ComparisonDetailOut> {
  const response = await fetch(`${API_BASE_URL}/comparisons/${id}`, { headers: _authHeaders() });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as ComparisonDetailOut;
}

/**
 * Published market wage distributions for a job family in a country.
 *
 * Unauthenticated on purpose: these are public government statistics, not
 * user-owned data. Note the backend answers "no data for this country"
 * with a 200 and available=false plus a stated reason, NOT an error and
 * NOT an empty list - so callers must render `unavailable_reason` rather
 * than treating a missing distribution as nothing to say.
 */
export async function fetchMarketContext(
  jobFamilyId: number,
  countryCode: string,
): Promise<MarketContextOut> {
  const params = new URLSearchParams({
    job_family_id: String(jobFamilyId),
    country_code: countryCode,
  });
  const response = await fetch(`${API_BASE_URL}/market-context?${params.toString()}`);
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as MarketContextOut;
}

export type AIInsightTarget = { calculationId: number } | { comparisonId: number };

// Deliberately idempotent-safe despite being a POST: the backend returns
// an already-passed cached result for the same target instead of
// re-generating (and re-billing) every time - see
// get_or_generate_insight's own caching logic. Requires auth, same as
// every comparison endpoint above - AI insight has no anonymous
// equivalent, since a real per-call cost needs a real identity to
// attach accountability to.
export async function createOrGetAIInsight(target: AIInsightTarget): Promise<AIInsightOut> {
  const body =
    'calculationId' in target
      ? { calculation_id: target.calculationId }
      : { comparison_id: target.comparisonId };

  const response = await fetch(`${API_BASE_URL}/ai-insights`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ..._authHeaders() },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as AIInsightOut;
}
