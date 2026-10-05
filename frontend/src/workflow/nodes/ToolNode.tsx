import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { useTranslation, type TranslationKey } from "../../i18n";
import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";
import { nodeCompletenessErrors } from "../validation/localValidation";

const TOOL_LABEL_KEYS: Record<string, TranslationKey> = {
  shell: "palette.shell.label",
  git: "palette.git.label",
  test_command: "palette.test.label",
};

export function ToolNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const { t } = useTranslation();
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  const command = node.config.command as string | undefined;
  const completeness = nodeCompletenessErrors(node);
  const firstIssue = completeness[0];
  const warning = firstIssue ? t(firstIssue.messageKey, firstIssue.messageParams) : null;
  const labelKey = TOOL_LABEL_KEYS[node.subtype];
  const label = labelKey ? t(labelKey) : t("palette.category.tool");
  const glyph = label.slice(0, 2).toUpperCase();

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category={label}
        glyph={glyph}
        warning={warning}
        summary={
          <>
            <span className="workflow-node-summary-line">{command ? command : t("node.notConfigured")}</span>
            {node.config.working_directory ? <span className="workflow-node-summary-muted">{String(node.config.working_directory)}</span> : null}
          </>
        }
      />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle" type="source" position={Position.Right} />
    </div>
  );
}
