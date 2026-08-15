import { useEffect, useMemo, useState, type FormEvent } from 'react';

import {
  fetchCountries,
  type ComponentType,
  type CompensationComponentIn,
  type CompensationInputCreate,
  type Country,
  type Currency,
} from '../../api/client';
import { COMPONENT_TYPE_LABELS, COMPONENT_TYPE_ORDER } from './labels';

interface ComponentRow {
  key: string;
  component_type: ComponentType;
  amount: string;
  currency_code: string;
  description: string;
}

let nextRowKey = 0;
function makeRow(currencyCode: string): ComponentRow {
  nextRowKey += 1;
  return {
    key: `row-${nextRowKey}`,
    component_type: 'base',
    amount: '',
    currency_code: currencyCode,
    description: '',
  };
}

type CountriesLoadState =
  | { kind: 'loading' }
  | { kind: 'loaded'; countries: Country[] }
  | { kind: 'error'; message: string };

export interface CompensationFormProps {
  onSubmit: (payload: CompensationInputCreate) => void;
  submitting?: boolean;
}

export function CompensationForm({ onSubmit, submitting = false }: CompensationFormProps) {
  const [countriesState, setCountriesState] = useState<CountriesLoadState>({ kind: 'loading' });
  const [countryCode, setCountryCode] = useState('');
  const [targetCurrencyCode, setTargetCurrencyCode] = useState('');
  const [rows, setRows] = useState<ComponentRow[]>([makeRow('')]);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;

    fetchCountries()
      .then((countries) => {
        if (cancelled) return;
        setCountriesState({ kind: 'loaded', countries });
        if (countries.length > 0) {
          const first = countries[0];
          setCountryCode(first.code);
          setTargetCurrencyCode(first.default_currency.code);
          setRows([makeRow(first.default_currency.code)]);
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : 'Unknown error';
        setCountriesState({ kind: 'error', message });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const countries = useMemo(
    () => (countriesState.kind === 'loaded' ? countriesState.countries : []),
    [countriesState],
  );

  const currencies = useMemo(() => {
    const byCode = new Map<string, Currency>();
    for (const country of countries) {
      byCode.set(country.default_currency.code, country.default_currency);
    }
    return [...byCode.values()].sort((a, b) => a.code.localeCompare(b.code));
  }, [countries]);

  function handleCountryChange(code: string) {
    setCountryCode(code);
    const country = countries.find((c) => c.code === code);
    if (country) {
      setTargetCurrencyCode(country.default_currency.code);
    }
  }

  function updateRow(key: string, patch: Partial<ComponentRow>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addRow() {
    setRows((current) => [...current, makeRow(targetCurrencyCode)]);
  }

  function removeRow(key: string) {
    setRows((current) => (current.length > 1 ? current.filter((row) => row.key !== key) : current));
  }

  function validate(): { errors: string[]; components: CompensationComponentIn[] } {
    const errors: string[] = [];

    if (!countryCode) {
      errors.push('Select a country.');
    }
    if (!targetCurrencyCode) {
      errors.push('Select a target currency.');
    }
    if (rows.length === 0) {
      errors.push('Add at least one compensation component.');
    }

    const components: CompensationComponentIn[] = [];
    rows.forEach((row, index) => {
      const position = index + 1;
      const amount = Number(row.amount);
      if (row.amount.trim() === '' || Number.isNaN(amount)) {
        errors.push(`Component ${position}: enter an amount.`);
      } else if (amount < 0) {
        errors.push(`Component ${position}: amount cannot be negative.`);
      }
      if (!row.currency_code) {
        errors.push(`Component ${position}: select a currency.`);
      }
      if (row.amount.trim() !== '' && !Number.isNaN(amount) && amount >= 0 && row.currency_code) {
        components.push({
          component_type: row.component_type,
          amount: row.amount,
          currency_code: row.currency_code,
          description: row.description.trim() === '' ? null : row.description.trim(),
        });
      }
    });

    return { errors, components };
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const { errors, components } = validate();
    setValidationErrors(errors);
    if (errors.length > 0) {
      return;
    }
    onSubmit({
      country_code: countryCode,
      target_currency_code: targetCurrencyCode,
      components,
    });
  }

  if (countriesState.kind === 'loading') {
    return <p>Loading countries…</p>;
  }

  if (countriesState.kind === 'error') {
    return <p role="alert">Could not load countries: {countriesState.message}</p>;
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {validationErrors.length > 0 && (
        <div role="alert" className="error-banner">
          <ul>
            {validationErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="field">
        <label htmlFor="country">Country</label>
        <select
          id="country"
          value={countryCode}
          onChange={(event) => handleCountryChange(event.target.value)}
        >
          {countries.map((country) => (
            <option key={country.code} value={country.code}>
              {country.name} ({country.code})
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="target-currency">Target currency</label>
        <select
          id="target-currency"
          value={targetCurrencyCode}
          onChange={(event) => setTargetCurrencyCode(event.target.value)}
        >
          {currencies.map((currency) => (
            <option key={currency.code} value={currency.code}>
              {currency.name} ({currency.code})
            </option>
          ))}
        </select>
      </div>

      <fieldset>
        <legend>Compensation components</legend>
        {rows.map((row, index) => (
          <div className="component-row" key={row.key}>
            <div className="field">
              <label htmlFor={`type-${row.key}`}>Type</label>
              <select
                id={`type-${row.key}`}
                value={row.component_type}
                onChange={(event) =>
                  updateRow(row.key, { component_type: event.target.value as ComponentType })
                }
              >
                {COMPONENT_TYPE_ORDER.map((type) => (
                  <option key={type} value={type}>
                    {COMPONENT_TYPE_LABELS[type]}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor={`amount-${row.key}`}>Amount</label>
              <input
                id={`amount-${row.key}`}
                type="number"
                min="0"
                step="0.01"
                value={row.amount}
                onChange={(event) => updateRow(row.key, { amount: event.target.value })}
              />
            </div>

            <div className="field">
              <label htmlFor={`currency-${row.key}`}>Currency</label>
              <select
                id={`currency-${row.key}`}
                value={row.currency_code}
                onChange={(event) => updateRow(row.key, { currency_code: event.target.value })}
              >
                {currencies.map((currency) => (
                  <option key={currency.code} value={currency.code}>
                    {currency.code}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={() => removeRow(row.key)}
              disabled={rows.length === 1}
              aria-label={`Remove component ${index + 1}`}
            >
              Remove
            </button>
          </div>
        ))}

        <button type="button" onClick={addRow}>
          Add component
        </button>
      </fieldset>

      <button type="submit" disabled={submitting}>
        {submitting ? 'Calculating…' : 'Calculate'}
      </button>
    </form>
  );
}
