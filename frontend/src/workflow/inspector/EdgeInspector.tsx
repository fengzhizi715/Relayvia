import type { WorkflowEdge } from "../../api/client";
import { useTranslation } from "../../i18n";
import { useWorkflowBuilderStore, useWorkflowNode } from "../store/workflowBuilderStore";
import { Field, TextField } from "./fields";

export function EdgeInspector({ edge }: { edge: WorkflowEdge }) {
  const { t } = useTranslation();
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);
  const updateEdge = useWorkflowBuilderStore((state) => state.updateEdge);
  const removeEdge = useWorkflowBuilderStore((state) => state.removeEdge);
  const source = useWorkflowNode(edge.source);
  const target = useWorkflowNode(edge.target);

  return (
    <div className="inspector-content">
      <div className="inspector-header">
        <div>
          <p className="eyebrow">{t("inspector.edgeEyebrow")}</p>
          <h4>{t("inspector.connection")}</h4>
        </div>
        {!readOnly && (
          <button className="icon-button icon-button--danger" type="button" aria-label={t("inspector.deleteConnection")} onClick={() => removeEdge(edge.id)}>
            ×
          </button>
        )}
      </div>
      <div className="inspector-form">
        <Field label={t("inspector.source")}>
          <TextField value={source?.name ?? edge.source} disabled />
        </Field>
        <Field label={t("inspector.target")}>
          <TextField value={target?.name ?? edge.target} disabled />
        </Field>
        <Field label={t("inspector.sourceHandle")}>
          <TextField value={edge.source_handle ?? t("inspector.defaultHandle")} disabled />
        </Field>
        <Field label={t("inspector.label")} hint={t("inspector.labelHint")}>
          <TextField value={edge.label ?? ""} onChange={(label) => updateEdge(edge.id, { label })} disabled={readOnly} placeholder="true" />
        </Field>
      </div>
      <div className="inspector-advanced">
        <span className="detail-label">{t("inspector.edgeId")}</span>
        <code>{edge.id}</code>
      </div>
    </div>
  );
}
