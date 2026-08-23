import type { Agent, Service, ServiceAction, WorkflowEdge, WorkflowNode } from "../../api/client";

export type IssueLevel = "error" | "warning";

export type NodeIssue = {
  code: string;
  level: IssueLevel;
  message: string;
  field?: string;
};

/**
 * Phase 4 edit-time validation. This is deliberately local UX validation only:
 * required fields, reference existence and service/action consistency. The
 * backend remains the final Graph Contract authority. Full topological /
 * Branch / cycle validation belongs to the server-side Graph Validation Engine.
 */
export function nodeCompletenessErrors(node: WorkflowNode): NodeIssue[] {
  const issues: NodeIssue[] = [];
  switch (node.type) {
    case "agent":
      if (!node.config.agent_id) {
        issues.push({ code: "AGENT_REQUIRED", level: "error", message: "Agent is required", field: "agent_id" });
      }
      break;
    case "service":
      if (!node.config.service_id) {
        issues.push({ code: "SERVICE_REQUIRED", level: "error", message: "Service is required", field: "service_id" });
      }
      if (!node.config.service_action_id) {
        issues.push({ code: "SERVICE_ACTION_REQUIRED", level: "error", message: "Service Action is required", field: "service_action_id" });
      }
      break;
    case "tool":
      if (!node.config.command) {
        issues.push({ code: "COMMAND_REQUIRED", level: "error", message: "Command is required", field: "command" });
      }
      break;
    case "logic":
      if (node.subtype === "condition") {
        const expression = node.config.expression as Record<string, unknown> | undefined;
        if (!expression || expression.left === "" || expression.left === null) {
          issues.push({ code: "CONDITION_LEFT_REQUIRED", level: "error", message: "Left value is required", field: "expression.left" });
        }
      }
      if (node.subtype === "wait") {
        const duration = Number(node.config.duration_seconds);
        if (!Number.isFinite(duration) || duration <= 0) {
          issues.push({ code: "WAIT_DURATION_REQUIRED", level: "error", message: "Duration must be greater than 0", field: "duration_seconds" });
        }
      }
      break;
    case "human":
      if (node.subtype === "approval" && !node.config.title) {
        issues.push({ code: "APPROVAL_TITLE_REQUIRED", level: "error", message: "Title is required", field: "title" });
      }
      break;
    case "data":
    default:
      break;
  }
  return issues;
}

export function nodeReferenceIssues(
  node: WorkflowNode,
  agents: Agent[],
  services: Service[],
  actionsById: Map<string, ServiceAction>,
): NodeIssue[] {
  const issues: NodeIssue[] = [];
  if (node.type === "agent") {
    const agentId = node.config.agent_id as string | undefined;
    if (agentId) {
      const agent = agents.find((item) => item.id === agentId);
      if (!agent) {
        issues.push({ code: "AGENT_NOT_FOUND", level: "error", message: "Agent not found", field: "agent_id" });
      } else if (!agent.enabled) {
        issues.push({ code: "AGENT_DISABLED", level: "warning", message: "Agent is disabled", field: "agent_id" });
      }
    }
  }
  if (node.type === "service") {
    const serviceId = node.config.service_id as string | undefined;
    const actionId = node.config.service_action_id as string | undefined;
    if (serviceId) {
      const service = services.find((item) => item.id === serviceId);
      if (!service) {
        issues.push({ code: "SERVICE_NOT_FOUND", level: "error", message: "Service not found", field: "service_id" });
      } else if (!service.enabled) {
        issues.push({ code: "SERVICE_DISABLED", level: "warning", message: "Service is disabled", field: "service_id" });
      }
      if (actionId) {
        const action = actionsById.get(actionId);
        if (!action) {
          issues.push({ code: "SERVICE_ACTION_NOT_FOUND", level: "error", message: "Service Action not found", field: "service_action_id" });
        } else if (action.service_id !== serviceId) {
          issues.push({ code: "SERVICE_ACTION_MISMATCH", level: "error", message: "Service Action does not belong to the selected Service", field: "service_action_id" });
        } else if (!action.enabled) {
          issues.push({ code: "SERVICE_ACTION_DISABLED", level: "warning", message: "Service Action is disabled", field: "service_action_id" });
        }
      }
    }
  }
  return issues;
}

export function nodeIssues(
  node: WorkflowNode,
  agents: Agent[],
  services: Service[],
  actionsById: Map<string, ServiceAction>,
): NodeIssue[] {
  return [...nodeCompletenessErrors(node), ...nodeReferenceIssues(node, agents, services, actionsById)];
}

export function nodeHasErrors(
  node: WorkflowNode,
  agents: Agent[],
  services: Service[],
  actionsById: Map<string, ServiceAction>,
): boolean {
  return nodeIssues(node, agents, services, actionsById).some((issue) => issue.level === "error");
}

export function edgeIssues(edge: WorkflowEdge, nodeIds: Set<string>): NodeIssue[] {
  const issues: NodeIssue[] = [];
  if (!nodeIds.has(edge.source)) {
    issues.push({ code: "EDGE_SOURCE_MISSING", level: "error", message: `Source node ${edge.source} does not exist`, field: "source" });
  }
  if (!nodeIds.has(edge.target)) {
    issues.push({ code: "EDGE_TARGET_MISSING", level: "error", message: `Target node ${edge.target} does not exist`, field: "target" });
  }
  return issues;
}
