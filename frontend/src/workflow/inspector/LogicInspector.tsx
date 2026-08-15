import type { WorkflowNode } from "../../api/client";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { ContextReferenceInput } from "../mapping/ContextReferenceInput";
import { Field, NumberField, SectionTitle, SelectField } from "./fields";

export const CONDITION_OPERATORS = ["==", "!=", ">", ">=", "<", "<=", "contains", "not_contains", "is_empty", "is_not_empty"];

export function LogicInspector({ node }: { node: WorkflowNode }) {
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);

  function setConfig(patch: Record<string, unknown>) {
    updateNode(node.id, { config: { ...node.config, ...patch } });
  }

  switch (node.subtype) {
    case "condition": {
      const expression = (node.config.expression as Record<string, unknown>) ?? {};
      return (
        <>
          <SectionTitle>Condition</SectionTitle>
          <Field label="Left value" hint="Compare a Context Reference against a constant or another value.">
            <ContextReferenceInput value={String(expression.left ?? "")} onChange={(left) => setConfig({ expression: { ...expression, left } })} disabled={readOnly} />
          </Field>
          <Field label="Operator">
            <SelectField value={String(expression.operator ?? "")} onChange={(operator) => setConfig({ expression: { ...expression, operator } })} disabled={readOnly}>
              {CONDITION_OPERATORS.map((operator) => (
                <option key={operator} value={operator}>
                  {operator}
                </option>
              ))}
            </SelectField>
          </Field>
          <Field label="Right value">
            <ContextReferenceInput value={String(expression.right ?? "")} onChange={(right) => setConfig({ expression: { ...expression, right } })} disabled={readOnly} placeholder="0.8" />
          </Field>
          <p className="field-hint">True / false branches are created from the two output handles on the canvas.</p>
        </>
      );
    }
    case "wait":
      return (
        <>
          <SectionTitle>Wait</SectionTitle>
          <Field label="Mode">
            <SelectField value={(node.config.mode as string) ?? "duration"} onChange={(mode) => setConfig({ mode })} disabled={readOnly || true}>
              <option value="duration">Duration</option>
            </SelectField>
          </Field>
          <Field label="Duration (seconds)">
            <NumberField value={(node.config.duration_seconds as number) ?? 60} onChange={(duration_seconds) => setConfig({ duration_seconds: Number.isFinite(duration_seconds) ? duration_seconds : 60 })} disabled={readOnly} min={1} />
          </Field>
        </>
      );
    case "merge":
      return (
        <>
          <SectionTitle>Merge</SectionTitle>
          <Field label="Strategy">
            <SelectField value={(node.config.strategy as string) ?? "all"} onChange={(strategy) => setConfig({ strategy })} disabled={readOnly}>
              <option value="all">All (wait for every branch)</option>
            </SelectField>
          </Field>
        </>
      );
    case "parallel":
      return (
        <>
          <SectionTitle>Parallel</SectionTitle>
          <p className="field-hint">Branches are expressed entirely by edges from the Parallel output handle. No branch list is stored in Node config.</p>
        </>
      );
    case "router":
      return (
        <>
          <SectionTitle>Router</SectionTitle>
          <p className="field-hint">Router semantics are reserved for a later phase. The node is not in the Palette but is preserved in existing Graphs.</p>
        </>
      );
    default:
      return null;
  }
}
