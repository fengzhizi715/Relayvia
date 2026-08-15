import { useState } from "react";

import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";

type ContextReferenceInputProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
};

type ReferenceOption = { label: string; insert: string };

/**
 * Text input for `{{...}}` Context References with a lightweight "Insert
 * reference" picker. Backend remains the final authority for reference
 * validation.
 */
export function ContextReferenceInput({ value, onChange, placeholder, disabled }: ContextReferenceInputProps) {
  const graph = useWorkflowBuilderStore((state) => state.graph);
  const [open, setOpen] = useState(false);

  const options: ReferenceOption[] = [];
  options.push({ label: "Workflow input", insert: "{{workflow.input." });
  for (const name of Object.keys(graph?.variables ?? {})) {
    options.push({ label: `Variable · ${name}`, insert: `{{workflow.variables.${name}}}` });
  }
  for (const node of graph?.nodes ?? []) {
    options.push({ label: `Node · ${node.name}`, insert: `{{nodes.${node.id}.output.` });
  }

  function insert(option: ReferenceOption) {
    onChange(value + option.insert);
    setOpen(false);
  }

  return (
    <div className="reference-input">
      <div className="reference-input-row">
        <input
          className="input code-input"
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder ?? "{{workflow.input.requirement}}"}
          spellCheck={false}
        />
        {!disabled && (
          <button className="button button--small" type="button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
            Insert reference
          </button>
        )}
      </div>
      {open && !disabled && (
        <div className="reference-menu" role="listbox" aria-label="Insert reference">
          {options.length === 0 ? (
            <span className="reference-menu-empty">No references available</span>
          ) : (
            options.map((option) => (
              <button className="reference-menu-item" key={option.label} type="button" role="option" onClick={() => insert(option)}>
                {option.label}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
