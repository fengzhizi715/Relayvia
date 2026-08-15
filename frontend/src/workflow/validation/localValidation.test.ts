import { describe, expect, it } from "vitest";

import type { Agent, Service, ServiceAction, WorkflowNode } from "../../api/client";
import { edgeIssues, nodeCompletenessErrors, nodeIssues } from "./localValidation";

function baseNode(overrides: Partial<WorkflowNode> = {}): WorkflowNode {
  return {
    id: "node-a",
    type: "agent",
    subtype: "agent",
    name: "Agent",
    position: { x: 0, y: 0 },
    config: {},
    input_mapping: {},
    metadata: {},
    ...overrides,
  };
}

const agent: Agent = { id: "agent-1", name: "Codex", enabled: true } as Agent;
const service: Service = { id: "service-1", name: "YoloWebAgent", enabled: true } as Service;
const action: ServiceAction = { id: "action-1", service_id: "service-1", name: "Start Training", enabled: true } as ServiceAction;
const otherAction: ServiceAction = { id: "action-2", service_id: "service-2", name: "Other", enabled: true } as ServiceAction;
const actionsById = new Map<string, ServiceAction>([
  [action.id, action],
  [otherAction.id, otherAction],
]);

describe("Phase 4 local validation", () => {
  it("requires an agent on Agent nodes", () => {
    const issues = nodeCompletenessErrors(baseNode({ config: { agent_id: "" } }));
    expect(issues).toEqual([expect.objectContaining({ code: "AGENT_REQUIRED", level: "error" })]);
    expect(nodeCompletenessErrors(baseNode({ config: { agent_id: "agent-1" } }))).toHaveLength(0);
  });

  it("requires a service and an action on Service nodes", () => {
    const node = baseNode({ type: "service", subtype: "http", config: {} });
    expect(nodeCompletenessErrors(node).map((issue) => issue.code)).toEqual(["SERVICE_REQUIRED", "SERVICE_ACTION_REQUIRED"]);
  });

  it("requires a command on Tool nodes", () => {
    const node = baseNode({ type: "tool", subtype: "shell", config: { command: "" } });
    expect(nodeCompletenessErrors(node)[0].code).toBe("COMMAND_REQUIRED");
  });

  it("validates condition expression and wait duration", () => {
    const condition = baseNode({ type: "logic", subtype: "condition", config: { expression: { left: "", operator: ">=", right: 0 } } });
    expect(nodeCompletenessErrors(condition)[0].code).toBe("CONDITION_LEFT_REQUIRED");
    const wait = baseNode({ type: "logic", subtype: "wait", config: { mode: "duration", duration_seconds: 0 } });
    expect(nodeCompletenessErrors(wait)[0].code).toBe("WAIT_DURATION_REQUIRED");
  });

  it("requires an approval title on Human Approval nodes", () => {
    const approval = baseNode({ type: "human", subtype: "approval", config: { title: "" } });
    expect(nodeCompletenessErrors(approval)[0].code).toBe("APPROVAL_TITLE_REQUIRED");
  });

  it("flags missing and disabled agent references", () => {
    const missing = nodeIssues(baseNode({ config: { agent_id: "ghost" } }), [], [], actionsById);
    expect(missing).toContainEqual(expect.objectContaining({ code: "AGENT_NOT_FOUND", level: "error" }));

    const disabled = nodeIssues(baseNode({ config: { agent_id: "agent-1" } }), [{ ...agent, enabled: false }], [], actionsById);
    expect(disabled).toContainEqual(expect.objectContaining({ code: "AGENT_DISABLED", level: "warning" }));
  });

  it("flags service action mismatch with the selected service", () => {
    const node = baseNode({ type: "service", subtype: "http", config: { service_id: "service-1", service_action_id: "action-2" } });
    const issues = nodeIssues(node, [], [service], actionsById);
    expect(issues).toContainEqual(expect.objectContaining({ code: "SERVICE_ACTION_MISMATCH", level: "error" }));
  });

  it("reports edges that reference missing nodes", () => {
    const issues = edgeIssues({ id: "e1", source: "a", target: "ghost" } as never, new Set(["a"]));
    expect(issues.map((issue) => issue.code)).toEqual(["EDGE_TARGET_MISSING"]);
  });
});
