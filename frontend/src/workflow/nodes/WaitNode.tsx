import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";
import { nodeCompletenessErrors } from "../validation/localValidation";

export function WaitNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  const duration = node.config.duration_seconds as number | undefined;
  const completeness = nodeCompletenessErrors(node);
  const warning = completeness[0]?.message ?? null;

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category="Wait"
        glyph="⏸"
        warning={warning}
        summary={<span className="workflow-node-summary-line workflow-node-summary-mono">{duration ? `${duration}s` : "Not configured"}</span>}
      />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle" type="source" position={Position.Right} />
    </div>
  );
}
