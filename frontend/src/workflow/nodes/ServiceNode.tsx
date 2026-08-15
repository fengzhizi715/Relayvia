import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { useServiceActions, useServices } from "../registry/useRegistry";
import { BaseWorkflowNode, useResolvedWorkflowNode } from "./BaseWorkflowNode";
import type { WorkflowReactFlowNodeData } from "../adapters/graphToReactFlow";
import { nodeCompletenessErrors } from "../validation/localValidation";

export function ServiceNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const node = useResolvedWorkflowNode(id, data);
  const { services } = useServices();
  const serviceId = (node?.config.service_id as string | undefined) ?? null;
  const { actions } = useServiceActions(serviceId);
  if (!node) return null;

  const actionId = node.config.service_action_id as string | undefined;
  const service = services.find((item) => item.id === serviceId);
  const action = actions.find((item) => item.id === actionId);
  const completeness = nodeCompletenessErrors(node);
  const warning = completeness[0]?.message ?? (serviceId && !service ? "Service not found" : actionId && !action ? "Service Action not found" : service && !service.enabled ? "Service is disabled" : null);

  return (
    <div className="workflow-node-root">
      <BaseWorkflowNode
        node={node}
        category="Service"
        glyph="SV"
        warning={warning}
        summary={
          <>
            <span className="workflow-node-summary-line">{service ? service.name : serviceId ? "Service unavailable" : "Not configured"}</span>
            {action ? (
              <span className="workflow-node-summary-muted">
                {action.method} {action.path}
              </span>
            ) : actionId ? (
              <span className="workflow-node-summary-muted">Action unavailable</span>
            ) : null}
          </>
        }
      />
      <Handle className="workflow-handle" type="target" position={Position.Left} />
      <Handle className="workflow-handle" type="source" position={Position.Right} />
    </div>
  );
}
