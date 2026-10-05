import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { useTranslation } from "../../i18n";
import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";
import { nodeCompletenessErrors } from "../validation/localValidation";

export function HumanNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const { t } = useTranslation();
  const node = useResolvedWorkflowNode(id, data);
  if (!node) return null;

  const isApproval = node.subtype === "approval";
  const title = node.config.title as string | undefined;
  const completeness = nodeCompletenessErrors(node);
  const firstIssue = completeness[0];
  const warning = firstIssue ? t(firstIssue.messageKey, firstIssue.messageParams) : null;

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category={isApproval ? t("palette.approval.label") : t("palette.humanInput.label")}
        glyph={isApproval ? "✓" : "?"}
        warning={warning}
        summary={
          <>
            <span className="workflow-node-summary-line">{isApproval ? (title ? title : t("node.notConfigured")) : t("node.collectHumanValues")}</span>
            {isApproval && node.config.description ? <span className="workflow-node-summary-muted">{String(node.config.description)}</span> : null}
          </>
        }
      />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle" type="source" position={Position.Right} />
    </div>
  );
}
