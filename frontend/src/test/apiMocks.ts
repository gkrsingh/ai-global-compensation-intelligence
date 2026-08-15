import { vi } from 'vitest';

import type {
  AccessTokenOut,
  CalculationOut,
  Country,
  PaginatedCalculationsOut,
  TaxRuleSet,
  TokenPairOut,
  UserOut,
} from '../api/client';

interface ErrorResponse {
  status: number;
  body: unknown;
}

interface FetchStubs {
  countries?: Country[];
  taxRuleSets?: Record<string, TaxRuleSet[]>;
  calculation?: CalculationOut | ErrorResponse;
  // Simulates the backend's X-Auth-Warning response header on the
  // calculation response, without needing a real expired token.
  calculationAuthWarning?: string;
  register?: UserOut | ErrorResponse;
  login?: TokenPairOut | ErrorResponse;
  refresh?: AccessTokenOut | ErrorResponse;
  logout?: ErrorResponse; // success is always a bare 204, nothing to configure
  myCalculations?: PaginatedCalculationsOut | ErrorResponse;
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return typeof value === 'object' && value !== null && 'status' in value && 'body' in value;
}

function mockResponse(
  ok: boolean,
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
) {
  return Promise.resolve({
    ok,
    status,
    json: () => Promise.resolve(body),
    headers: { get: (name: string) => headers[name] ?? null },
  });
}

function respondFrom(
  value: unknown,
  successStatus: number,
  headers: Record<string, string> = {},
): ReturnType<typeof mockResponse> {
  if (value && isErrorResponse(value)) {
    return mockResponse(false, value.status, value.body);
  }
  return mockResponse(true, successStatus, value, headers);
}

/**
 * A single global fetch mock, dispatching by URL/method, standing in for
 * every real endpoint the calculator and auth features call. Mirrors
 * HealthStatus.test.tsx's vi.stubGlobal('fetch', ...) pattern, extended
 * to route by URL since these components hit more than one endpoint.
 */
export function stubFetch(stubs: FetchStubs) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    const method = init?.method ?? 'GET';

    const taxRuleSetsMatch = /\/countries\/([^/]+)\/tax-rule-sets/.exec(url);
    if (taxRuleSetsMatch) {
      return mockResponse(true, 200, stubs.taxRuleSets?.[taxRuleSetsMatch[1]] ?? []);
    }

    if (url.endsWith('/countries')) {
      return mockResponse(true, 200, stubs.countries ?? []);
    }

    if (url.includes('/calculations/mine')) {
      return respondFrom(
        stubs.myCalculations ?? { items: [], total: 0, limit: 20, offset: 0 },
        200,
      );
    }

    if (url.endsWith('/calculations') && method === 'POST') {
      const headers: Record<string, string> = stubs.calculationAuthWarning
        ? { 'X-Auth-Warning': stubs.calculationAuthWarning }
        : {};
      return respondFrom(stubs.calculation, 201, headers);
    }

    if (url.endsWith('/auth/register')) {
      return respondFrom(stubs.register, 201);
    }
    if (url.endsWith('/auth/login')) {
      return respondFrom(stubs.login, 200);
    }
    if (url.endsWith('/auth/refresh')) {
      return respondFrom(stubs.refresh, 200);
    }
    if (url.endsWith('/auth/logout')) {
      if (stubs.logout) {
        return mockResponse(false, stubs.logout.status, stubs.logout.body);
      }
      return mockResponse(true, 204, null);
    }

    return Promise.reject(new Error(`Unhandled fetch in test: ${url}`));
  });

  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

export const CURRENCY_USD = { code: 'USD', name: 'US Dollar', symbol: '$' };
export const CURRENCY_INR = { code: 'INR', name: 'Indian Rupee', symbol: '₹' };
export const CURRENCY_EUR = { code: 'EUR', name: 'Euro', symbol: '€' };

export const COUNTRIES: Country[] = [
  { code: 'ES', name: 'Spain', default_currency: CURRENCY_EUR },
  { code: 'IN', name: 'India', default_currency: CURRENCY_INR },
  { code: 'US', name: 'United States', default_currency: CURRENCY_USD },
];
