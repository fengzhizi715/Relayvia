import { describe, expect, it } from "vitest";

import { PALETTE_ITEMS, createWorkflowNode, generateEdgeId, generateNodeId } from "./nodeFactory";

describe("Workflow Node factory", () => {
  it("produces a Graph Contract 1.0 compliant Node for every palette item", () => {
    expect(PALETTE_ITEMS.length).toBe(14);
    for (const item of PALETTE_ITEMS) {
      const node = createWorkflowNode(item.type, item.subtype, { x: 12, y: 34 });
      expect(node.id).toMatch(/^[A-Za-z0-9][A-Za-z0-9_-]*$/);
      expect(node.type).toBe(item.type);
      expect(node.subtype).toBe(item.subtype);
      expect(node.name).toBe(item.defaultName);
      expect(node.position).toEqual({ x: 12, y: 34 });
      expect(typeof node.config).toBe("object");
      expect(node.input_mapping).toEqual({});
      expect(node.metadata).toEqual({});
    }
  });

  it("generates unique node and edge ids", () => {
    const ids = new Set<string>();
    for (let index = 0; index < 50; index += 1) {
      ids.add(generateNodeId());
      ids.add(generateEdgeId());
    }
    expect(ids.size).toBe(100);
  });

  it("gives new nodes valid default configs per subtype", () => {
    const condition = createWorkflowNode("logic", "condition", { x: 0, y: 0 });
    expect(condition.config.expression).toEqual({ left: "", operator: ">=", right: 0 });

    const wait = createWorkflowNode("logic", "wait", { x: 0, y: 0 });
    expect(wait.config).toEqual({ mode: "duration", duration_seconds: 60 });

    const approval = createWorkflowNode("human", "approval", { x: 0, y: 0 });
    expect(approval.config).toEqual({ title: "", description: "", allow_reject: true });

    const agent = createWorkflowNode("agent", "agent", { x: 0, y: 0 });
    expect(agent.config.agent_id).toBe("");
  });

  it("rejects unknown type/subtype combinations", () => {
    expect(() => createWorkflowNode("logic", "router", { x: 0, y: 0 })).toThrow();
    expect(() => createWorkflowNode("data", "unknown", { x: 0, y: 0 })).toThrow();
  });

  it("does not expose provider-specific palette items (Codex / Cursor / YoloWebAgent)", () => {
    const labels = PALETTE_ITEMS.map((item) => item.label.toLowerCase());
    expect(labels).not.toContain("codex");
    expect(labels).not.toContain("cursor");
    expect(labels).not.toContain("yolowebagent");
  });
});
