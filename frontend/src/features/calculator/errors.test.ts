import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import { friendlyErrorLines } from './errors';

describe('friendlyErrorLines', () => {
  it('adds the illustrative-rates note for missing_exchange_rate', () => {
    const lines = friendlyErrorLines(
      new ApiError('missing_exchange_rate', 'No exchange rate available for INR -> EUR', null),
    );
    expect(lines[0]).toBe('No exchange rate available for INR -> EUR');
    expect(lines[1]).toMatch(/illustrative exchange rates seeded/);
  });

  it('gives a plain-language nudge for ambiguous_tax_rule_set', () => {
    const lines = friendlyErrorLines(
      new ApiError('ambiguous_tax_rule_set', 'Multiple tax rule sets apply for IN...', null),
    );
    expect(lines[0]).toMatch(/Pick a tax regime/);
  });

  it('formats validation_error details into one readable line per field', () => {
    const details = [
      {
        type: 'greater_than_equal',
        loc: ['body', 'components', 0, 'amount'],
        msg: 'Input should be greater than or equal to 0',
        input: '-100',
        ctx: { ge: 0 },
      },
    ];
    const lines = friendlyErrorLines(
      new ApiError('validation_error', 'Request validation failed', details),
    );
    expect(lines).toEqual(['components #1 amount: Input should be greater than or equal to 0']);
  });

  it('falls back to a generic message when validation details are missing or malformed', () => {
    expect(
      friendlyErrorLines(new ApiError('validation_error', 'Request validation failed', null)),
    ).toEqual(['Please check your input and try again.']);
    expect(
      friendlyErrorLines(
        new ApiError('validation_error', 'Request validation failed', ['not an object']),
      ),
    ).toEqual(['Invalid value.']);
  });

  it('shows the raw backend message for codes with no special handling', () => {
    const lines = friendlyErrorLines(
      new ApiError('unknown_country', 'Unknown country code: ZZ', null),
    );
    expect(lines).toEqual(['Unknown country code: ZZ']);
  });
});
