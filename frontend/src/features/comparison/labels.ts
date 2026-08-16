// Mirrors app.comparison.services.normalize.GAP_METRICS - the three
// metrics gap analysis is computed over (total_tax_amount is shown per
// entry but deliberately excluded there, see that module's docstring).
export const GAP_METRIC_ORDER = ['gross_amount', 'total_compensation_amount', 'net_amount'];

export const GAP_METRIC_LABELS: Record<string, string> = {
  gross_amount: 'Gross compensation',
  total_compensation_amount: 'Total compensation',
  net_amount: 'Net compensation',
};

export function gapMetricLabel(metric: string): string {
  return GAP_METRIC_LABELS[metric] ?? metric;
}
