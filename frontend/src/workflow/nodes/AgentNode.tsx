import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { useTranslation } from "../../i18n";
import { useAgents } from "../registry/useRegistry";
import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";
import { nodeCompletenessErrors } from "../validation/localValidation";

function glyph(role: string | undefined) {
  return role ? role.slice(0, 2).toUpperCase() : "AG";
}

export function AgentNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const { t } = useTranslation();
  const node = useResolvedWorkflowNode(id, data);
  const { agents } = useAgents();
  if (!node) return null;

  const agentId = node.config.agent_id as string | undefined;
  const agent = agents.find((item) => item.id === agentId);
  const completeness = nodeCompletenessErrors(node);
  const firstIssue = completeness[0];
  const warning = firstIssue
    ? t(firstIssue.messageKey, firstIssue.messageParams)
    : agentId && !agent ? t("node.agentNotFound") : agent && !agent.enabled ? t("node.agentDisabled") : null;

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category={t("palette.agent.label")}
        glyph={glyph(node.config.role as string | undefined)}
        warning={warning}
        summary={
          <>
            <span className="workflow-node-summary-line">{agent ? agent.name : agentId ? t("node.agentUnavailable") : t("node.notConfigured")}</span>
            {node.config.role ? <span className="workflow-node-summary-muted">{String(node.config.role)}</span> : null}
          </>
        }
      />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle" type="source" position={Position.Right} />
    </div>
  );
}
