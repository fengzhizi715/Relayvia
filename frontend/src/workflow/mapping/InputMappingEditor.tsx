import { useState } from "react";

import { ContextReferenceInput } from "./ContextReferenceInput";

type InputMappingEditorProps = {
  mapping: Record<string, unknown>;
  onChange: (mapping: Record<string, unknown>) => void;
  disabled?: boolean;
  hint?: string;
};

/**
 * Shared key / value editor for Node `input_mapping` and for Data Node
 * mapping-style configs (transform mappings, output_mapping).
 */
export function InputMappingEditor({ mapping, onChange, disabled, hint }: InputMappingEditorProps) {
  const [error, setError] = useState<string | null>(null);
  const entries = Object.entries(mapping);

  function setKey(oldKey: string, newKey: string) {
    if (!newKey.trim()) return;
    if (newKey !== oldKey && Object.prototype.hasOwnProperty.call(mapping, newKey)) {
      setError(`Key "${newKey}" already exists.`);
      return;
    }
    setError(null);
    const next: Record<string, unknown> = {};
    for (const [key, value] of entries) next[key === oldKey ? newKey : key] = value;
    onChange(next);
  }

  function setValue(key: string, value: string) {
    const next = { ...mapping, [key]: value };
    onChange(next);
  }

  function remove(key: string) {
    const next: Record<string, unknown> = {};
    for (const [existingKey, value] of entries) {
      if (existingKey !== key) next[existingKey] = value;
    }
    onChange(next);
  }

  function add() {
    onChange({ ...mapping, new_key: "" });
  }

  return (
    <div className="mapping-editor">
      {entries.length === 0 ? (
        <span className="field-hint">No mappings yet.</span>
      ) : (
        <div className="mapping-rows">
          {entries.map(([key, value]) => (
            <div className="mapping-row" key={key}>
              <input
                className="input mapping-key"
                aria-label="Mapping key"
                value={key}
                disabled={disabled}
                onChange={(event) => setKey(key, event.target.value)}
              />
              <ContextReferenceInput value={typeof value === "string" ? value : JSON.stringify(value)} onChange={(value) => setValue(key, value)} disabled={disabled} />
              {!disabled && (
                <button className="icon-button icon-button--danger" type="button" aria-label={`Remove mapping ${key}`} onClick={() => remove(key)}>
                  ×
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {!disabled && (
        <button className="text-button" type="button" onClick={add}>
          + Add mapping
        </button>
      )}
      {hint && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}
