export function formatCurrency(amount: string, currencyCode: string): string {
  const value = Number(amount);
  if (Number.isNaN(value)) {
    return `${amount} ${currencyCode}`;
  }
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currencyCode }).format(
      value,
    );
  } catch {
    // Intl.NumberFormat throws for an unrecognized ISO 4217 code - fall
    // back to plain text rather than crash the results view over it.
    return `${amount} ${currencyCode}`;
  }
}

export function formatRate(rate: string): string {
  const value = Number(rate);
  if (Number.isNaN(value)) {
    return rate;
  }
  return `${(value * 100).toFixed(2)}%`;
}
