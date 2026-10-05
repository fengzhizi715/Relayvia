import { useReactFlow } from "@xyflow/react";

import type { ValidationIssue } from "../../api/client";
import { useTranslation } from "../../i18n";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";

type ValidationPanelProps = {
  onClose: () => void;
};

/**
 * Backend Full Validation results. Rows are clickable: node issues select and
 * focus the node, edge issues select the edge and fit its endpoints.
 */
export function ValidationPanel({ onClose }: ValidationPanelProps) {
  const { t } = useTranslation();
  const validation = useWorkflowBuilderStore((state) => state.validation);
  const validationStale = useWorkflowBuilderStore((state) => state.validationStale);
  const graph = useWorkflowBuilderStore((state) => state.graph);
  const selectNode = useWorkflowBuilderStore((state) => state.selectNode);
  const selectEdge = useWorkflowBuilderStore((state) => state.selectEdge);
  const { fitView } = useReactFlow();

  if (!validation) return null;

  const errors = validation.issues.filter((issue) => issue.severity === "error");
  const warnings = validation.issues.filter((issue) => issue.severity === "warning");

  function focus(issue: ValidationIssue) {
    if (issue.node_id) {
      selectNode(issue.node_id);
      fitView({ nodes: [{ id: issue.node_id }], padding: 0.35, duration: 300 });
      return;
    }
    if (issue.edge_id && graph) {
      const edge = graph.edges.find((item) => item.id === issue.edge_id);
      selectEdge(issue.edge_id);
      if (edge) {
        fitView({ nodes: [{ id: edge.source }, { id: edge.target }], padding: 0.45, duration: 300 });
      }
    }
  }

  function location(issue: ValidationIssue): string {
    if (issue.node_id) return t("validation.locationNode", { id: issue.node_id });
    if (issue.edge_id) return t("validation.locationEdge", { id: issue.edge_id });
    return t("validation.locationWorkflow");
  }

  return (
    <section className="validation-panel" aria-label={t("validation.aria")}>
      <div className="validation-panel-header">
        <div>
          <p className="eyebrow">{t("validation.eyebrow")}</p>
          <h4>
            {validation.valid ? t("validation.valid") : t("validation.invalid")}
            <span className="validation-panel-counts">
              {t(errors.length === 1 ? "toolbar.errorOne" : "toolbar.errorMany", { count: errors.length })} · {t(warnings.length === 1 ? "toolbar.warningOne" : "toolbar.warningMany", { count: warnings.length })}
            </span>
          </h4>
        </div>
        <button className="icon-button" type="button" aria-label={t("validation.close")} onClick={onClose}>
          ×
        </button>
      </div>
      {validationStale && <div className="validation-stale">{t("validation.stale")}</div>}
      <div className="validation-groups">
        {errors.length > 0 && (
          <div className="validation-group">
            <span className="validation-group-label validation-group-label--error">{t("validation.errors")}</span>
            {errors.map((issue) => (
              <button className="validation-row validation-row--error" key={`${issue.code}-${issue.node_id}-${issue.field}`} type="button" onClick={() => focus(issue)}>
                <span className="validation-row-dot" aria-hidden="true" />
                <span className="validation-row-copy">
                  <span className="validation-row-message">{issue.message}</span>
                  <span className="validation-row-location">{location(issue)}</span>
                </span>
              </button>
            ))}
          </div>
        )}
        {warnings.length > 0 && (
          <div className="validation-group">
            <span className="validation-group-label">{t("validation.warnings")}</span>
            {warnings.map((issue) => (
              <button className="validation-row validation-row--warning" key={`${issue.code}-${issue.node_id}-${issue.field}`} type="button" onClick={() => focus(issue)}>
                <span className="validation-row-dot" aria-hidden="true" />
                <span className="validation-row-copy">
                  <span className="validation-row-message">{issue.message}</span>
                  <span className="validation-row-location">{location(issue)}</span>
                </span>
              </button>
            ))}
          </div>
        )}
        {errors.length === 0 && warnings.length === 0 && (
          <div className="validation-clean">{t("validation.clean")}</div>
        )}
      </div>
    </section>
  );
}
