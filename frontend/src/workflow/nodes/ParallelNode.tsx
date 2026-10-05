import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { useTranslation } from "../../i18n";
import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";

export function ParallelNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const { t } = useTranslation();
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode node={node} category={t("palette.parallel.label")} glyph="∥" summary={<span className="workflow-node-summary-line">{t("node.fanOut")}</span>} />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle" type="source" position={Position.Right} />
    </div>
  );
}
