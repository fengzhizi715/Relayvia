import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";
import { nodeCompletenessErrors } from "../validation/localValidation";

const TOOL_LABELS: Record<string, string> = {
  shell: "Shell",
  git: "Git",
  test_command: "Test Command",
};

export function ToolNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  const command = node.config.command as string | undefined;
  const completeness = nodeCompletenessErrors(node);
  const warning = completeness[0]?.message ?? null;
  const glyph = (TOOL_LABELS[node.subtype] ?? "Tool").slice(0, 2).toUpperCase();

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category={TOOL_LABELS[node.subtype] ?? "Tool"}
        glyph={glyph}
        warning={warning}
        summary={
          <>
            <span className="workflow-node-summary-line">{command ? command : "Not configured"}</span>
            {node.config.working_directory ? <span className="workflow-node-summary-muted">{String(node.config.working_directory)}</span> : null}
          </>
        }
      />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle" type="source" position={Position.Right} />
    </div>
  );
}
