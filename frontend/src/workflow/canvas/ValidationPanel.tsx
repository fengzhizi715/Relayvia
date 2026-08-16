import { useReactFlow } from "@xyflow/react";

import type { ValidationIssue } from "../../api/client";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";

type ValidationPanelProps = {
  onClose: () => void;
};

/**
 * Backend Full Validation results. Rows are clickable: node issues select and
 * focus the node, edge issues select the edge and fit its endpoints.
 */
export function ValidationPanel({ onClose }: ValidationPanelProps) {
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

  return (
    <section className="validation-panel" aria-label="Workflow validation results">
      <div className="validation-panel-header">
        <div>
          <p className="eyebrow">VALIDATION</p>
          <h4>
            {validation.valid ? "Valid" : "Invalid"}
            <span className="validation-panel-counts">
              {errors.length} error{errors.length === 1 ? "" : "s"} · {warnings.length} warning{warnings.length === 1 ? "" : "s"}
            </span>
          </h4>
        </div>
        <button className="icon-button" type="button" aria-label="Close validation panel" onClick={onClose}>
          ×
        </button>
      </div>
      {validationStale && <div className="validation-stale">Graph changed since this validation. Re-run Validate.</div>}
      <div className="validation-groups">
        {errors.length > 0 && (
          <div className="validation-group">
            <span className="validation-group-label validation-group-label--error">Errors</span>
            {errors.map((issue) => (
              <button className="validation-row validation-row--error" key={`${issue.code}-${issue.node_id}-${issue.field}`} type="button" onClick={() => focus(issue)}>
                <span className="validation-row-dot" aria-hidden="true" />
                <span className="validation-row-copy">
                  <span className="validation-row-message">{issue.message}</span>
                  <span className="validation-row-location">{issue.node_id ? `Node ${issue.node_id}` : issue.edge_id ? `Edge ${issue.edge_id}` : "Workflow-level"}</span>
                </span>
              </button>
            ))}
          </div>
        )}
        {warnings.length > 0 && (
          <div className="validation-group">
            <span className="validation-group-label">Warnings</span>
            {warnings.map((issue) => (
              <button className="validation-row validation-row--warning" key={`${issue.code}-${issue.node_id}-${issue.field}`} type="button" onClick={() => focus(issue)}>
                <span className="validation-row-dot" aria-hidden="true" />
                <span className="validation-row-copy">
                  <span className="validation-row-message">{issue.message}</span>
                  <span className="validation-row-location">{issue.node_id ? `Node ${issue.node_id}` : issue.edge_id ? `Edge ${issue.edge_id}` : "Workflow-level"}</span>
                </span>
              </button>
            ))}
          </div>
        )}
        {errors.length === 0 && warnings.length === 0 && (
          <div className="validation-clean">Workflow passes full validation. Warnings and errors are shown here when present.</div>
        )}
      </div>
    </section>
  );
}
