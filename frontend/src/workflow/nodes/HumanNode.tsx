import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";
import { nodeCompletenessErrors } from "../validation/localValidation";

export function HumanNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  const isApproval = node.subtype === "approval";
  const title = node.config.title as string | undefined;
  const completeness = nodeCompletenessErrors(node);
  const warning = completeness[0]?.message ?? null;

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category={isApproval ? "Approval" : "Human Input"}
        glyph={isApproval ? "✓" : "?"}
        warning={warning}
        summary={
          <>
            <span className="workflow-node-summary-line">{isApproval ? (title ? title : "Not configured") : "Collect human values"}</span>
            {isApproval && node.config.description ? <span className="workflow-node-summary-muted">{String(node.config.description)}</span> : null}
          </>
        }
      />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle" type="source" position={Position.Right} />
    </div>
  );
}
