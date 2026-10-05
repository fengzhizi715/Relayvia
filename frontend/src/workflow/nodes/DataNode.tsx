import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { useTranslation, type TranslationKey } from "../../i18n";
import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";

const DATA_LABEL_KEYS: Record<string, TranslationKey> = {
  input: "palette.input.label",
  transform: "palette.transform.label",
  output: "palette.output.label",
};

export function DataNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const { t } = useTranslation();
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  const labelKey = DATA_LABEL_KEYS[node.subtype];
  const label = labelKey ? t(labelKey) : t("palette.data.label");
  const glyph = label.slice(0, 2).toUpperCase();
  const isInput = node.subtype === "input";
  const isOutput = node.subtype === "output";

  let summary = t("node.inputSchema");
  if (node.subtype === "transform") {
    const count = Object.keys((node.config.mappings as Record<string, unknown>) ?? {}).length;
    summary = count ? t(count === 1 ? "node.mappingOne" : "node.mappingMany", { count }) : t("node.noMappings");
  } else if (node.subtype === "output") {
    const count = Object.keys((node.config.output_mapping as Record<string, unknown>) ?? {}).length;
    summary = count ? t(count === 1 ? "node.outputOne" : "node.outputMany", { count }) : t("node.noOutputs");
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
