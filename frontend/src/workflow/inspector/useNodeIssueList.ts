import { useMemo } from "react";

import type { WorkflowNode } from "../../api/client";
import { useAgents, useServiceActions, useServices } from "../registry/useRegistry";
import { nodeIssues, type NodeIssue } from "../validation/localValidation";

export function useNodeIssueList(node: WorkflowNode): NodeIssue[] {
  const { agents } = useAgents();
  const { services } = useServices();
  const serviceId = node.type === "service" ? (node.config.service_id as string | null) ?? null : null;
  const { actions } = useServiceActions(serviceId);
  const actionsById = useMemo(() => new Map(actions.map((action) => [action.id, action])), [actions]);
  return useMemo(() => nodeIssues(node, agents, services, actionsById), [node, agents, services, actionsById]);
}
