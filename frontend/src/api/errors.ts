import type { ApiError } from './client';

interface ValidationDetail {
  loc?: unknown;
  msg?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function formatValidationDetails(details: unknown): string[] {
  if (!Array.isArray(details) || details.length === 0) {
    return ['Please check your input and try again.'];
  }
  return details.map((item: unknown) => {
    if (!isRecord(item)) return 'Invalid value.';
    const detail = item as ValidationDetail;
    const loc = Array.isArray(detail.loc) ? detail.loc : [];
    const msg = typeof detail.msg === 'string' ? detail.msg : 'Invalid value.';
    // loc looks like ["body", "components", 0, "amount"] - drop the
    // "body" wrapper FastAPI always adds, since it's meaningless to a
    // reader who never sees the request envelope.
    const field = loc
      .filter((part) => part !== 'body')
      .map((part) => (typeof part === 'number' ? `#${part + 1}` : part))
      .join(' ');
    return field ? `${field}: ${msg}` : msg;
  });
}

/**
 * Maps a backend ApiError to plain-language lines for display. Shared
 * across features (calculator, auth) since it's generic - most codes
 * already carry a human-phrased message from the backend and don't need
 * special-casing; only codes that need extra context beyond their raw
 * message are handled explicitly here.
 */
export function friendlyErrorLines(error: ApiError): string[] {
  switch (error.code) {
    case 'missing_exchange_rate':
      return [
        error.message,
        'This project currently tracks real exchange rates for USD, INR, and EUR only (fetched on a schedule from a live provider), so a currency outside that set will legitimately fail here.',
      ];
    case 'ambiguous_tax_rule_set':
      return [
        'This country has more than one applicable tax rule set for the date you selected. Pick a tax regime above and try again.',
      ];
    case 'validation_error':
      return formatValidationDetails(error.details);
    default:
      return [error.message];
  }
}
