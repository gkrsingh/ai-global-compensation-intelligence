import { vi } from 'vitest';

import type { CalculationOut, Country, TaxRuleSet } from '../api/client';

interface ErrorResponse {
  status: number;
  body: unknown;
}

interface FetchStubs {
  countries?: Country[];
  taxRuleSets?: Record<string, TaxRuleSet[]>;
  calculation?: CalculationOut | ErrorResponse;
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return typeof value === 'object' && value !== null && 'status' in value && 'body' in value;
}

/**
 * A single global fetch mock, dispatching by URL/method, standing in for
 * the three real endpoints the calculator feature calls. Mirrors
 * HealthStatus.test.tsx's vi.stubGlobal('fetch', ...) pattern, extended
 * to route by URL since these components hit more than one endpoint.
 */
export function stubFetch(stubs: FetchStubs) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();

      const taxRuleSetsMatch = /\/countries\/([^/]+)\/tax-rule-sets/.exec(url);
      if (taxRuleSetsMatch) {
        const ruleSets = stubs.taxRuleSets?.[taxRuleSetsMatch[1]] ?? [];
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(ruleSets),
        });
      }

      if (url.endsWith('/countries')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(stubs.countries ?? []),
        });
      }

      if (url.endsWith('/calculations') && init?.method === 'POST') {
        const calculation = stubs.calculation;
        if (calculation && isErrorResponse(calculation)) {
          return Promise.resolve({
            ok: false,
            status: calculation.status,
            json: () => Promise.resolve(calculation.body),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 201,
          json: () => Promise.resolve(calculation),
        });
      }

      return Promise.reject(new Error(`Unhandled fetch in test: ${url}`));
    }),
  );
}

export const CURRENCY_USD = { code: 'USD', name: 'US Dollar', symbol: '$' };
export const CURRENCY_INR = { code: 'INR', name: 'Indian Rupee', symbol: '₹' };
export const CURRENCY_EUR = { code: 'EUR', name: 'Euro', symbol: '€' };

export const COUNTRIES: Country[] = [
  { code: 'ES', name: 'Spain', default_currency: CURRENCY_EUR },
  { code: 'IN', name: 'India', default_currency: CURRENCY_INR },
  { code: 'US', name: 'United States', default_currency: CURRENCY_USD },
];
