// The backend types Calculation.breakdown as an untyped JSONB dict
// (dict[str, Any] in Pydantic, {[key: string]: unknown} in the generated
// schema) because it's a free-form audit trail, not a versioned API
// contract. These types mirror app/compensation/engine.py's actual
// construction of that dict so the results view can render it - with a
// runtime check (parseBreakdown) rather than a blind cast, since nothing
// enforces this shape stays in sync beyond both sides being read by a
// human.

export interface BreakdownComponent {
  type: string;
  description: string | null;
  original_amount: string;
  original_currency: string;
  converted_amount: string;
  counts_toward_gross: boolean;
}

export interface TaxBracketDetail {
  lower_bound: string;
  upper_bound: string | null;
  rate: string;
  taxable_amount: string;
  tax_amount: string;
}

export interface TaxComponentBreakdown {
  component: string;
  taxable_base: string;
  total_tax: string;
  brackets: TaxBracketDetail[];
}

export interface TaxBreakdown {
  rule_set_id: number;
  rule_set_name: string;
  // The tax rule set's own currency (e.g. INR for India) - can differ
  // from CalculationBreakdown.target_currency when the caller asks to
  // see totals in a different currency than the tax law is denominated
  // in. standard_deduction/taxable_base/bracket amounts below are all in
  // THIS currency, never target_currency.
  currency: string;
  standard_deduction: string | null;
  components: TaxComponentBreakdown[];
}

export interface CalculationBreakdown {
  target_currency: string;
  as_of_date: string;
  rates_used: Record<string, string>;
  components: BreakdownComponent[];
  tax: TaxBreakdown | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function parseBreakdown(breakdown: unknown): CalculationBreakdown | null {
  if (!isRecord(breakdown)) return null;
  const { target_currency, as_of_date, rates_used, components } = breakdown;
  if (
    typeof target_currency !== 'string' ||
    typeof as_of_date !== 'string' ||
    !isRecord(rates_used) ||
    !Array.isArray(components)
  ) {
    return null;
  }

  return {
    target_currency,
    as_of_date,
    rates_used: rates_used as Record<string, string>,
    components: components as BreakdownComponent[],
    tax: isRecord(breakdown.tax) ? (breakdown.tax as unknown as TaxBreakdown) : null,
  };
}
