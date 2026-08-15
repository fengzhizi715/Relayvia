import type { WorkflowEdge } from "../../api/client";
import { useWorkflowBuilderStore, useWorkflowNode } from "../store/workflowBuilderStore";
import { Field, TextField } from "./fields";

export function EdgeInspector({ edge }: { edge: WorkflowEdge }) {
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);
  const updateEdge = useWorkflowBuilderStore((state) => state.updateEdge);
  const removeEdge = useWorkflowBuilderStore((state) => state.removeEdge);
  const source = useWorkflowNode(edge.source);
  const target = useWorkflowNode(edge.target);

  return (
    <div className="inspector-content">
      <div className="inspector-header">
        <div>
          <p className="eyebrow">EDGE INSPECTOR</p>
          <h4>Connection</h4>
        </div>
        {!readOnly && (
          <button className="icon-button icon-button--danger" type="button" aria-label="Delete connection" onClick={() => removeEdge(edge.id)}>
            ×
          </button>
        )}
      </div>
      <div className="inspector-form">
        <Field label="Source">
          <TextField value={source?.name ?? edge.source} disabled />
        </Field>
        <Field label="Target">
          <TextField value={target?.name ?? edge.target} disabled />
        </Field>
        <Field label="Source handle">
          <TextField value={edge.source_handle ?? "default"} disabled />
        </Field>
        <Field label="Label" hint="Visual only. Condition semantics come from the source handle.">
          <TextField value={edge.label ?? ""} onChange={(label) => updateEdge(edge.id, { label })} disabled={readOnly} placeholder="true" />
        </Field>
      </div>
      <div className="inspector-advanced">
        <span className="detail-label">Edge ID</span>
        <code>{edge.id}</code>
      </div>
    </div>
  );
}
