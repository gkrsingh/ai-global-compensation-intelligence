import type { ComponentType } from '../../api/client';

export const COMPONENT_TYPE_ORDER: ComponentType[] = [
  'base',
  'bonus',
  'equity',
  'benefit',
  'allowance',
];

export const COMPONENT_TYPE_LABELS: Record<ComponentType, string> = {
  base: 'Base salary',
  bonus: 'Bonus',
  equity: 'Equity',
  benefit: 'Benefit',
  allowance: 'Allowance',
};

// Mirrors the backend's TaxComponent enum (app/reference_data/models.py) -
// deliberately generic so a future country's own named levy just adds an
// entry here, not a new code path.
export const TAX_COMPONENT_LABELS: Record<string, string> = {
  income_tax: 'Income tax',
  social_security: 'Social security',
  medicare: 'Medicare',
  medicare_additional_surtax: 'Medicare additional surtax',
};

export function componentTypeLabel(type: string): string {
  return COMPONENT_TYPE_LABELS[type as ComponentType] ?? type;
}

export function taxComponentLabel(component: string): string {
  return TAX_COMPONENT_LABELS[component] ?? component;
}
