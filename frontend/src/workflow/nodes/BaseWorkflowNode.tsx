import { useMemo, type ReactNode } from "react";

import type { WorkflowNode } from "../../api/client";
import { useWorkflowBuilderStore, useWorkflowNode } from "../store/workflowBuilderStore";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";

type BaseWorkflowNodeProps = {
  node: WorkflowNode;
  category: string;
  glyph: string;
  tone?: string;
  summary?: ReactNode;
  warning?: string | null;
};

export function BaseWorkflowNode({ node, category, glyph, tone = category.toLowerCase(), summary, warning }: BaseWorkflowNodeProps) {
  const validation = useWorkflowBuilderStore((state) => state.validation);
  const backend = useMemo(() => {
    if (!validation) return { errors: [] as string[], warnings: [] as string[] };
    const errors: string[] = [];
    const warnings: string[] = [];
    for (const issue of validation.issues) {
      if (issue.node_id !== node.id) continue;
      if (issue.severity === "error") errors.push(issue.message);
      else warnings.push(issue.message);
    }
    return { errors, warnings };
  }, [validation, node.id]);

  const errorBadge = backend.errors[0] ?? null;
  const warningBadge = !errorBadge && backend.warnings.length > 0 ? backend.warnings[0] : null;

  return (
    <div className={`workflow-node workflow-node--${tone}`}>
      {errorBadge ? (
        <div className="workflow-node-warning" title={backend.errors.join("\n")} role="status">
          ⚠ {errorBadge}
        </div>
      ) : warningBadge ? (
        <div className="workflow-node-warning workflow-node-warning--amber" title={backend.warnings.join("\n")} role="status">
          ⚠ {warningBadge}
        </div>
      ) : warning ? (
        <div className="workflow-node-warning workflow-node-warning--amber" title={warning} role="status">
          ⚠ {warning}
        </div>
      ) : null}
      <div className="workflow-node-header">
        <span className="workflow-node-glyph" aria-hidden="true">
          {glyph}
        </span>
        <div className="workflow-node-title">
          <span className="workflow-node-category">{category}</span>
          <strong className="workflow-node-name">{node.name || node.id}</strong>
        </div>
      </div>
      {summary ? <div className="workflow-node-summary">{summary}</div> : null}
    </div>
  );
}

/**
 * Reads the live Workflow Node from the Builder store (source of truth) and
 * falls back to the React Flow `data` snapshot before the store is ready.
 */
export function useResolvedWorkflowNode(id: string, data: WorkflowReactFlowNodeData | undefined): WorkflowNode | null {
  const live = useWorkflowNode(id);
  return live ?? data?.workflowNode ?? null;
}
