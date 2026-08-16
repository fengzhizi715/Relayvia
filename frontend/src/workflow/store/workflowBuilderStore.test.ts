import { beforeEach, describe, expect, it } from "vitest";

import type { WorkflowGraph } from "../../api/client";
import { useWorkflowBuilderStore } from "./workflowBuilderStore";

const EMPTY: WorkflowGraph = { schema_version: "1.0", nodes: [], edges: [], variables: {}, metadata: {} };

function seed() {
  useWorkflowBuilderStore.getState().initialize({
    workflowId: "workflow-1",
    workflowName: "Coding Showcase",
    graph: EMPTY,
    mode: { kind: "draft" },
    readOnly: false,
  });
}

beforeEach(() => {
  useWorkflowBuilderStore.getState().reset();
  seed();
});

describe("Workflow builder store", () => {
  it("adds a node, marks the graph dirty and selects it", () => {
    const id = useWorkflowBuilderStore.getState().addNode("agent", "agent", { x: 10, y: 20 });
    const state = useWorkflowBuilderStore.getState();
    expect(state.graph?.nodes).toHaveLength(1);
    expect(state.graph?.nodes[0].id).toBe(id);
    expect(state.graph?.nodes[0].config.agent_id).toBe("");
    expect(state.isDirty).toBe(true);
    expect(state.selectedNodeId).toBe(id);
  });

  it("updates a node config and name without changing its id", () => {
    const id = useWorkflowBuilderStore.getState().addNode("agent", "agent", { x: 0, y: 0 });
    useWorkflowBuilderStore.getState().updateNode(id, { name: "Planner", config: { agent_id: "agent-1" } });
    const node = useWorkflowBuilderStore.getState().graph!.nodes[0];
    expect(node.id).toBe(id);
    expect(node.name).toBe("Planner");
    expect(node.config.agent_id).toBe("agent-1");
  });

  it("adds an edge with a condition source handle and selects it", () => {
    const source = useWorkflowBuilderStore.getState().addNode("logic", "condition", { x: 0, y: 0 });
    const target = useWorkflowBuilderStore.getState().addNode("human", "approval", { x: 0, y: 0 });
    useWorkflowBuilderStore.getState().addEdge(source, target, "true");
    const edge = useWorkflowBuilderStore.getState().graph!.edges[0];
    expect(edge.source).toBe(source);
    expect(edge.target).toBe(target);
    expect(edge.source_handle).toBe("true");
    expect(edge.label).toBe("true");
    expect(useWorkflowBuilderStore.getState().selectedEdgeId).toBe(edge.id);
    expect(useWorkflowBuilderStore.getState().selectedNodeId).toBeNull();
  });

  it("rejects self connections and edges to missing nodes", () => {
    const node = useWorkflowBuilderStore.getState().addNode("data", "output", { x: 0, y: 0 });
    useWorkflowBuilderStore.getState().addEdge(node, node);
    expect(useWorkflowBuilderStore.getState().graph!.edges).toHaveLength(0);
    useWorkflowBuilderStore.getState().addEdge(node, "missing");
    expect(useWorkflowBuilderStore.getState().graph!.edges).toHaveLength(0);
  });

  it("removes a node and all connected edges", () => {
    const a = useWorkflowBuilderStore.getState().addNode("data", "input", { x: 0, y: 0 });
    const b = useWorkflowBuilderStore.getState().addNode("agent", "agent", { x: 0, y: 0 });
    const c = useWorkflowBuilderStore.getState().addNode("data", "output", { x: 0, y: 0 });
    useWorkflowBuilderStore.getState().addEdge(a, b);
    useWorkflowBuilderStore.getState().addEdge(b, c);
    expect(useWorkflowBuilderStore.getState().graph!.edges).toHaveLength(2);
    useWorkflowBuilderStore.getState().removeNode(b);
    const graph = useWorkflowBuilderStore.getState().graph!;
    expect(graph.nodes.map((node) => node.id)).not.toContain(b);
    expect(graph.edges).toHaveLength(0);
  });

  it("tracks dirty state through move / save / edit / save-fail", () => {
    const id = useWorkflowBuilderStore.getState().addNode("data", "input", { x: 0, y: 0 });
    useWorkflowBuilderStore.getState().markSaved("2026-08-15T00:00:00Z");
    expect(useWorkflowBuilderStore.getState().isDirty).toBe(false);

    useWorkflowBuilderStore.getState().moveNode(id, { x: 50, y: 60 });
    expect(useWorkflowBuilderStore.getState().isDirty).toBe(true);

    useWorkflowBuilderStore.getState().markSaved("2026-08-15T00:00:01Z");
    expect(useWorkflowBuilderStore.getState().isDirty).toBe(false);

    useWorkflowBuilderStore.getState().updateNode(id, { name: "Renamed" });
    expect(useWorkflowBuilderStore.getState().isDirty).toBe(true);

    useWorkflowBuilderStore.getState().setSaveError("boom");
    expect(useWorkflowBuilderStore.getState().isDirty).toBe(true);
    expect(useWorkflowBuilderStore.getState().saveError).toBe("boom");
  });

  it("does not mark dirty when moving a node to the same position", () => {
    const id = useWorkflowBuilderStore.getState().addNode("data", "input", { x: 5, y: 5 });
    useWorkflowBuilderStore.getState().markSaved("2026-08-15T00:00:00Z");
    useWorkflowBuilderStore.getState().moveNode(id, { x: 5, y: 5 });
    expect(useWorkflowBuilderStore.getState().isDirty).toBe(false);
  });

  it("ignores edits in read-only mode", () => {
    useWorkflowBuilderStore.getState().initialize({
      workflowId: "workflow-1",
      workflowName: "Coding Showcase",
      graph: { ...EMPTY, nodes: [{ id: "n1", type: "data", subtype: "input", name: "In", position: { x: 0, y: 0 }, config: {}, input_mapping: {}, metadata: {} }] },
      mode: { kind: "version", version: 3, changeNote: null },
      readOnly: true,
    });
    const state = useWorkflowBuilderStore.getState();
    const before = state.graph!.nodes[0].name;
    state.updateNode("n1", { name: "Changed" });
    state.addNode("agent", "agent", { x: 1, y: 1 });
    state.removeNode("n1");
    const after = useWorkflowBuilderStore.getState();
    expect(after.graph!.nodes).toHaveLength(1);
    expect(after.graph!.nodes[0].name).toBe(before);
    expect(after.isDirty).toBe(false);
  });

  it("tracks backend validation results and staleness", () => {
    const id = useWorkflowBuilderStore.getState().addNode("data", "input", { x: 0, y: 0 });
    useWorkflowBuilderStore.getState().setValidation(
      {
        valid: false,
        errors: [{ code: "X", severity: "error", message: "boom", node_id: id, edge_id: null, field: null, details: {} }],
        warnings: [],
      },
      "2026-08-15T00:00:00Z",
    );
    let state = useWorkflowBuilderStore.getState();
    expect(state.validationStale).toBe(false);
    expect(state.validation?.valid).toBe(false);
    expect(state.validation?.issues).toHaveLength(1);

    state.moveNode(id, { x: 10, y: 10 });
    expect(useWorkflowBuilderStore.getState().validationStale).toBe(false);

    state.updateNode(id, { name: "Renamed" });
    expect(useWorkflowBuilderStore.getState().validationStale).toBe(true);
  });
});
