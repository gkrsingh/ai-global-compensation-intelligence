import type { components } from './schema';

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

export async function fetchTaxRuleSets(countryCode: string): Promise<TaxRuleSet[]> {
  const response = await fetch(`${API_BASE_URL}/countries/${countryCode}/tax-rule-sets`);
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as TaxRuleSet[];
}

export async function createCalculation(payload: CompensationInputCreate): Promise<CalculationOut> {
  const response = await fetch(`${API_BASE_URL}/calculations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return (await response.json()) as CalculationOut;
}
