import { useEffect, useState } from "react";

type JsonEditorProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  hint?: string;
  readOnly?: boolean;
};

export function JsonEditor({ label, value, onChange, rows = 6, hint, readOnly = false }: JsonEditorProps) {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
  }, [value]);

  function format() {
    try {
      onChange(JSON.stringify(JSON.parse(value), null, 2));
      setError(null);
    } catch {
      setError("Enter valid JSON before formatting.");
    }
  }

  return (
    <div className="field field--json">
      <div className="field-label-row">
        <label>{label}</label>
        {!readOnly && <button className="text-button" type="button" onClick={format}>Format</button>}
      </div>
      <textarea readOnly={readOnly} className={error ? "input input--error code-input" : "input code-input"} rows={rows} value={value} onChange={(event) => onChange(event.target.value)} />
      {hint && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}
