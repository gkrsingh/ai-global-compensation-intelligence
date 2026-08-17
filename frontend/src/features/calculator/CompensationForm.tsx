import { useEffect, useMemo, useState, type FormEvent } from 'react';

import {
  fetchCountries,
  fetchTaxRuleSets,
  type ComponentType,
  type CompensationComponentIn,
  type CompensationInputCreate,
  fetchJobFamilies,
  type JobFamily,
  type Country,
  type Currency,
} from '../../api/client';
import { COMPONENT_TYPE_LABELS, COMPONENT_TYPE_ORDER, regimeLabel } from './labels';

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
  const [regimeOptions, setRegimeOptions] = useState<string[]>([]);
  const [regime, setRegime] = useState('');
  const [jobFamilies, setJobFamilies] = useState<JobFamily[]>([]);
  // Optional on purpose: the calculator has always worked without a job
  // family and must keep doing so. Selecting one only unlocks the market
  // context panel, which needs a family to map onto a published
  // occupation - it is never required to compute a result.
  const [jobFamilyId, setJobFamilyId] = useState<string>('');

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

  useEffect(() => {
    let cancelled = false;
    // A failure here must never block the calculator: job family is
    // optional, so an empty list simply means no market context, not a
    // broken form.
    fetchJobFamilies()
      .then((families) => {
        if (!cancelled) setJobFamilies(families);
      })
      .catch(() => {
        if (!cancelled) setJobFamilies([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!countryCode) {
      setRegimeOptions([]);
      setRegime('');
      return;
    }
    let cancelled = false;

    fetchTaxRuleSets(countryCode)
      .then((ruleSets) => {
        if (cancelled) return;
        const distinctRegimes = [
          ...new Set(ruleSets.map((rs) => rs.regime).filter((r): r is string => r !== null)),
        ];
        setRegimeOptions(distinctRegimes);
        setRegime(distinctRegimes.length > 1 ? distinctRegimes[0] : '');
      })
      .catch(() => {
        // Non-fatal: if this lookup fails, the form still works fine for
        // countries with an unambiguous (single) tax rule set. A country
        // that actually needs disambiguation would surface a clear
        // ambiguous_tax_rule_set error on submit instead - better than
        // silently guessing a regime.
        if (cancelled) return;
        setRegimeOptions([]);
        setRegime('');
      });

    return () => {
      cancelled = true;
    };
  }, [countryCode]);

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
    if (regimeOptions.length > 1 && !regime) {
      errors.push('Select a tax regime.');
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
      regime: regimeOptions.length > 1 ? regime : null,
      job_family_id: jobFamilyId === '' ? null : Number(jobFamilyId),
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

      {jobFamilies.length > 0 && (
        <div className="field">
          <label htmlFor="job-family">Job family (optional)</label>
          <select
            id="job-family"
            value={jobFamilyId}
            onChange={(event) => setJobFamilyId(event.target.value)}
          >
            <option value="">Not specified</option>
            {jobFamilies.map((family) => (
              <option key={family.id} value={String(family.id)}>
                {family.name}
              </option>
            ))}
          </select>
          <p className="field-hint">
            Only used to show published market wage statistics alongside your result. It does not
            affect any calculated figure.
          </p>
        </div>
      )}

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

      {regimeOptions.length > 1 && (
        <div className="field">
          <label htmlFor="regime">Tax regime</label>
          <select id="regime" value={regime} onChange={(event) => setRegime(event.target.value)}>
            {regimeOptions.map((option) => (
              <option key={option} value={option}>
                {regimeLabel(option)}
              </option>
            ))}
          </select>
        </div>
      )}

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
