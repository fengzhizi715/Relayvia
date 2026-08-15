import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";

const DATA_LABELS: Record<string, string> = {
  input: "Input",
  transform: "Transform",
  output: "Output",
};

export function DataNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  const label = DATA_LABELS[node.subtype] ?? "Data";
  const glyph = label.slice(0, 2).toUpperCase();
  const isInput = node.subtype === "input";
  const isOutput = node.subtype === "output";

  let summary = "Input schema";
  if (node.subtype === "transform") {
    const count = Object.keys((node.config.mappings as Record<string, unknown>) ?? {}).length;
    summary = count ? `${count} mapping${count === 1 ? "" : "s"}` : "No mappings";
  } else if (node.subtype === "output") {
    const count = Object.keys((node.config.output_mapping as Record<string, unknown>) ?? {}).length;
    summary = count ? `${count} output${count === 1 ? "" : "s"}` : "No outputs";
  }

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category={label}
        glyph={glyph}
        summary={<span className="workflow-node-summary-line">{summary}</span>}
      />
      {!isInput && <Handle className="workflow-handle" type="target" position={Position.Left} />}
      {!isOutput && <Handle className="workflow-handle" type="source" position={Position.Right} />}
    </div>
  );
}
