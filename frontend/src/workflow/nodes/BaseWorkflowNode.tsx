import type { ReactNode } from "react";

import type { WorkflowNode } from "../../api/client";
import { useWorkflowNode } from "../store/workflowBuilderStore";
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
  return (
    <div className={`workflow-node workflow-node--${tone}`}>
      {warning ? (
        <div className="workflow-node-warning" title={warning} role="status">
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
