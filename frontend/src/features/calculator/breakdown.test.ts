import { describe, expect, it } from 'vitest';

import { parseBreakdown } from './breakdown';

describe('parseBreakdown', () => {
  it('parses a well-formed breakdown', () => {
    const result = parseBreakdown({
      target_currency: 'USD',
      as_of_date: '2026-01-01',
      rates_used: {},
      components: [],
      tax: null,
    });

    expect(result).not.toBeNull();
    expect(result?.target_currency).toBe('USD');
    expect(result?.tax).toBeNull();
  });

  it('returns null for a non-object value', () => {
    expect(parseBreakdown('not an object')).toBeNull();
    expect(parseBreakdown(null)).toBeNull();
    expect(parseBreakdown(undefined)).toBeNull();
  });

  it('returns null when required fields are missing or the wrong type', () => {
    expect(parseBreakdown({ target_currency: 'USD' })).toBeNull();
    expect(
      parseBreakdown({
        target_currency: 123,
        as_of_date: '2026-01-01',
        rates_used: {},
        components: [],
      }),
    ).toBeNull();
  });
});
