import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { useTranslation } from "../../i18n";
import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";

export function MergeNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const { t } = useTranslation();
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  const strategy = (node.config.strategy as string | undefined) ?? "all";
  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category={t("palette.merge.label")}
        glyph="⨝"
        summary={<span className="workflow-node-summary-line workflow-node-summary-mono">{strategy.toUpperCase()}</span>}
      />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle" type="source" position={Position.Right} />
    </div>
  );
}
