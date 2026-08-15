import { describe, expect, it } from "vitest";

import type { WorkflowGraph } from "../../api/client";
import { graphToReactFlow, nodeReactFlowType, reconcileWorkflowEdges, reconcileWorkflowNodes } from "./graphToReactFlow";
import { reactFlowToGraph } from "./reactFlowToGraph";

function sampleGraph(): WorkflowGraph {
  return {
    schema_version: "1.0",
    nodes: [
      { id: "input", type: "data", subtype: "input", name: "Requirement", position: { x: 0, y: 100 }, config: { schema: { type: "object" } }, input_mapping: {}, metadata: {} },
      { id: "planner", type: "agent", subtype: "agent", name: "Planner", position: { x: 300, y: 100 }, config: { agent_id: "agent-1", timeout_seconds: 600 }, input_mapping: { task: "{{workflow.input.requirement}}" }, metadata: {} },
      { id: "condition", type: "logic", subtype: "condition", name: "Pass?", position: { x: 600, y: 100 }, config: { expression: { left: "{{nodes.planner.output.score}}", operator: ">=", right: 0.8 } }, input_mapping: {}, metadata: {} },
      { id: "approval", type: "human", subtype: "approval", name: "Approve", position: { x: 900, y: 100 }, config: { title: "Approve?" }, input_mapping: {}, metadata: {} },
      { id: "output", type: "data", subtype: "output", name: "Output", position: { x: 1200, y: 100 }, config: { output_mapping: { result: "{{nodes.approval.output.status}}" } }, input_mapping: {}, metadata: {} },
    ],
    edges: [
      { id: "e1", source: "input", target: "planner", source_handle: null, target_handle: null, label: null, condition: null, metadata: {} },
      { id: "e2", source: "planner", target: "condition", source_handle: null, target_handle: null, label: null, condition: null, metadata: {} },
      { id: "e3", source: "condition", target: "approval", source_handle: "true", target_handle: null, label: "true", condition: null, metadata: {} },
      { id: "e4", source: "approval", target: "output", source_handle: null, target_handle: null, label: null, condition: null, metadata: {} },
    ],
    variables: { threshold: { type: "number", default: 0.8, description: "min" } },
    metadata: {},
  };
}

describe("Workflow Graph <-> React Flow adapter", () => {
  it("round-trips a graph through React Flow without losing domain semantics", () => {
    const graph = sampleGraph();
    const { nodes, edges } = graphToReactFlow(graph);
    const restored = reactFlowToGraph(graph, nodes, edges);
    expect(restored).toEqual(graph);
  });

  it("keeps React Flow node and edge ids identical to Graph ids", () => {
    const graph = sampleGraph();
    const { nodes, edges } = graphToReactFlow(graph);
    expect(nodes.map((node) => node.id)).toEqual(graph.nodes.map((node) => node.id));
    expect(edges.map((edge) => edge.id)).toEqual(graph.edges.map((edge) => edge.id));
  });

  it("maps every Graph node type/subtype to a React Flow node type", () => {
    expect(nodeReactFlowType({ ...sampleGraph().nodes[0], id: "x" })).toBe("data");
    expect(nodeReactFlowType({ ...sampleGraph().nodes[1], id: "x" })).toBe("agent");
    expect(nodeReactFlowType({ ...sampleGraph().nodes[2], id: "x" })).toBe("condition");
    expect(nodeReactFlowType({ ...sampleGraph().nodes[3], id: "x" })).toBe("human");
    expect(nodeReactFlowType({ type: "service", subtype: "http", id: "x", name: "s", position: { x: 0, y: 0 }, config: {}, input_mapping: {}, metadata: {} })).toBe("service");
    expect(nodeReactFlowType({ type: "tool", subtype: "shell", id: "x", name: "t", position: { x: 0, y: 0 }, config: {}, input_mapping: {}, metadata: {} })).toBe("tool");
    expect(nodeReactFlowType({ type: "logic", subtype: "parallel", id: "x", name: "p", position: { x: 0, y: 0 }, config: {}, input_mapping: {}, metadata: {} })).toBe("parallel");
    expect(nodeReactFlowType({ type: "logic", subtype: "merge", id: "x", name: "m", position: { x: 0, y: 0 }, config: {}, input_mapping: {}, metadata: {} })).toBe("merge");
    expect(nodeReactFlowType({ type: "logic", subtype: "wait", id: "x", name: "w", position: { x: 0, y: 0 }, config: {}, input_mapping: {}, metadata: {} })).toBe("wait");
    expect(nodeReactFlowType({ type: "logic", subtype: "router", id: "x", name: "r", position: { x: 0, y: 0 }, config: {}, input_mapping: {}, metadata: {} })).toBe("router");
  });

  it("maps condition handles to React Flow source handles and back", () => {
    const graph = sampleGraph();
    const { edges } = graphToReactFlow(graph);
    const conditionEdge = edges.find((edge) => edge.id === "e3");
    expect(conditionEdge?.sourceHandle).toBe("true");
    expect(conditionEdge?.label).toBe("true");
    const restored = reactFlowToGraph(graph, [], edges);
    expect(restored.edges.find((edge) => edge.id === "e3")?.source_handle).toBe("true");
  });

  it("preserves React Flow rendering state (measured, selection) on reconcile", () => {
    const graph = sampleGraph();
    const { nodes, edges } = graphToReactFlow(graph, { nodeId: "planner", edgeId: "e3" });
    const withLayout = nodes.map((node) => ({ ...node, measured: { width: 220, height: 120 }, selected: node.id === "planner" }));
    const reconciled = reconcileWorkflowNodes(graph, withLayout);
    expect(reconciled.find((node) => node.id === "planner")?.measured).toEqual({ width: 220, height: 120 });
    expect(reconciled.find((node) => node.id === "planner")?.selected).toBe(true);

    const selectedEdges = edges.map((edge) => ({ ...edge, selected: edge.id === "e3" }));
    const reconciledEdges = reconcileWorkflowEdges(graph, selectedEdges);
    expect(reconciledEdges.find((edge) => edge.id === "e3")?.selected).toBe(true);
  });

  it("pulls React Flow position and label changes back into the domain graph only", () => {
    const graph = sampleGraph();
    const { nodes, edges } = graphToReactFlow(graph);
    const moved = nodes.map((node) => (node.id === "planner" ? { ...node, position: { x: 999, y: 777 } } : node));
    const relabeled = edges.map((edge) => (edge.id === "e3" ? { ...edge, label: "passed" } : edge));
    const restored = reactFlowToGraph(graph, moved, relabeled);
    expect(restored.nodes.find((node) => node.id === "planner")?.position).toEqual({ x: 999, y: 777 });
    expect(restored.edges.find((edge) => edge.id === "e3")?.label).toBe("passed");
    expect(restored.nodes.find((node) => node.id === "input")?.position).toEqual({ x: 0, y: 100 });
  });
});
