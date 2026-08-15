import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";

export function ConditionNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  const expression = node.config.expression as Record<string, unknown> | undefined;
  const summary = expression
    ? `${String(expression.left ?? "")} ${String(expression.operator ?? "")} ${String(expression.right ?? "")}`
    : "Not configured";

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category="Condition"
        glyph="IF"
        summary={<span className="workflow-node-summary-line workflow-node-summary-mono">{summary}</span>}
      />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle workflow-handle--true" type="source" position={Position.Right} id="true" style={{ top: "38%" }} />
      <Handle className="workflow-handle workflow-handle--false" type="source" position={Position.Right} id="false" style={{ top: "72%" }} />
      <span className="workflow-handle-label workflow-handle-label--true">true</span>
      <span className="workflow-handle-label workflow-handle-label--false">false</span>
    </div>
  );
}
