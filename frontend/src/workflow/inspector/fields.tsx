import type { ReactNode } from "react";

import type { NodeIssue } from "../validation/localValidation";

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

type TextFieldProps = {
  value: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
};

export function TextField({ value, onChange, placeholder, disabled }: TextFieldProps) {
  return <input className="input" value={value} onChange={(event) => onChange?.(event.target.value)} placeholder={placeholder} disabled={disabled} />;
}

type NumberFieldProps = {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  min?: number;
  max?: number;
};

export function NumberField({ value, onChange, disabled, min, max }: NumberFieldProps) {
  return (
    <input
      className="input"
      type="number"
      min={min}
      max={max}
      value={Number.isFinite(value) ? value : ""}
      onChange={(event) => onChange(event.target.value === "" ? NaN : Number(event.target.value))}
      disabled={disabled}
    />
  );
}

type SelectFieldProps = {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  children?: ReactNode;
};

export function SelectField({ value, onChange, disabled, placeholder, children }: SelectFieldProps) {
  return (
    <select className="input" value={value ?? ""} onChange={(event) => onChange(event.target.value)} disabled={disabled}>
      {placeholder ? <option value="">{placeholder}</option> : null}
      {children}
    </select>
  );
}

type TextAreaFieldProps = {
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
  disabled?: boolean;
};

export function TextAreaField({ value, onChange, rows = 3, placeholder, disabled }: TextAreaFieldProps) {
  return <textarea className="input" rows={rows} value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} disabled={disabled} />;
}

export function CheckboxField({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return (
    <label className="field field--checkbox">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} disabled={disabled} />
    </label>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <p className="form-section-title">{children}</p>;
}

import { useEffect, useState } from "react";

type JsonConfigFieldProps = {
  label: string;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  rows?: number;
  disabled?: boolean;
  hint?: string;
};

export function JsonConfigField({ label, value, onChange, rows = 6, disabled, hint }: JsonConfigFieldProps) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!error) setText(JSON.stringify(value, null, 2));
  }, [value, error]);

  function handleChange(next: string) {
    setText(next);
    try {
      const parsed = JSON.parse(next);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("must be an object");
      setError(null);
      onChange(parsed as Record<string, unknown>);
    } catch {
      setError("Enter valid JSON before saving.");
    }
  }

  return (
    <div className="field field--json">
      <div className="field-label-row">
        <label>{label}</label>
      </div>
      <textarea
        className={error ? "input input--error code-input" : "input code-input"}
        rows={rows}
        value={text}
        disabled={disabled}
        onChange={(event) => handleChange(event.target.value)}
        spellCheck={false}
      />
      {hint && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}

export function IssueList({ issues }: { issues: NodeIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <div className="inspector-issues">
      {issues.map((issue) => (
        <div key={issue.code} className={`inspector-issue inspector-issue--${issue.level}`}>
          {issue.message}
        </div>
      ))}
    </div>
  );
}
